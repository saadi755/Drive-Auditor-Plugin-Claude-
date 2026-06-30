"""
engine.py
=========
Pure scan logic. Every function takes (provider, config) explicitly — no module
globals, so concurrent scans with different settings never interfere.

Concurrency uses ThreadPoolExecutor (the Google client is blocking IO, so
threads, not asyncio). Each worker builds its OWN Drive service, because those
services are not safe to share across threads. Every API call is wrapped in
with_retry, and a user that still fails after retries is recorded as a warning,
never silently dropped.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional

from googleapiclient.errors import HttpError

from .backoff import with_retry
from .config import ScanConfig
from .logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class UserResult:
    email: str
    files: list[dict] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ScanResult:
    users_scanned: int
    files_in_report: int
    total_bytes: int
    results: list[dict]
    warnings: list[str]


def human(n: float) -> str:
    """Human-readable byte size. Unchanged from the original script."""
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def list_all_users(provider, config: ScanConfig) -> list[str]:
    """Every primary email in the org (impersonating the admin)."""
    service = provider.directory_service()
    users: list[str] = []
    page_token = None
    while True:
        resp = with_retry(
            lambda: service.users().list(
                customer="my_customer", maxResults=500, orderBy="email",
                pageToken=page_token, projection="basic",
            ).execute(),
            max_retries=config.max_retries,
        )
        for u in resp.get("users", []):
            if config.include_suspended or not u.get("suspended"):
                users.append(u["primaryEmail"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return users


def largest_files_for_user(provider, email: str, config: ScanConfig) -> UserResult:
    """Top-N files owned by one user, ordered by quota bytes. Builds its own
    Drive service so it is safe to call from a worker thread."""
    try:
        service = provider.drive_service(email)
        resp = with_retry(
            lambda: service.files().list(
                q="'me' in owners and trashed = false",
                orderBy="quotaBytesUsed desc",
                pageSize=config.top_files_per_user,
                corpora="user",
                fields="files(id,name,mimeType,quotaBytesUsed,modifiedTime)",
            ).execute(),
            max_retries=config.max_retries,
        )
    except HttpError as e:
        return UserResult(email=email, error=f"HTTP {getattr(e.resp, 'status', '?')}")
    except Exception as e:  # noqa: BLE001
        return UserResult(email=email, error=str(e))

    files = [{
        "owner": email,
        "name": f.get("name", ""),
        "bytes": int(f.get("quotaBytesUsed", "0")),
        "mimeType": f.get("mimeType", ""),
        "modified": f.get("modifiedTime", ""),
        "id": f.get("id", ""),
    } for f in resp.get("files", [])]
    return UserResult(email=email, files=files)


def scan_org(provider, config: ScanConfig,
             *, progress: Optional[Callable[[int, int], None]] = None) -> ScanResult:
    """Scan every user concurrently and return the combined largest-files report."""
    users = list_all_users(provider, config)
    total = len(users)
    log.info("scan started", extra={"users": total})

    all_files: list[dict] = []
    warnings: list[str] = []
    done = 0

    with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
        futures = {
            pool.submit(largest_files_for_user, provider, email, config): email
            for email in users
        }
        for fut in as_completed(futures):
            result = fut.result()
            if result.error:
                warnings.append(f"{result.email}: {result.error}")
            else:
                all_files.extend(result.files)
            done += 1
            if progress:
                progress(done, total)

    all_files.sort(key=lambda x: x["bytes"], reverse=True)
    top = all_files[: config.top_files_overall]
    log.info("scan finished",
             extra={"files_in_report": len(top), "warnings": len(warnings)})

    return ScanResult(
        users_scanned=total,
        files_in_report=len(top),
        total_bytes=sum(f["bytes"] for f in top),
        results=top,
        warnings=warnings,
    )
