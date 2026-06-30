"""
mcp_server.py
=============
Claude-facing tools for the Drive auditor, now on a JOB API: start a scan, get a
job_id back immediately, then poll status/results. Every tool builds a fresh
per-call ScanConfig (no global mutation).

Phase 1 gets credentials from a local FileCredentialProvider via env vars, all
isolated in get_provider(). Phase 2 replaces ONLY the body of get_provider()
with a Secrets-Manager fetch keyed by tenant — nothing else moves.

Env vars required:
    GWS_KEY_FILE     path to the service-account JSON key
    GWS_ADMIN_EMAIL  a Workspace super admin
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict

# Make the src/ package importable no matter where Claude launches this from.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from mcp.server.fastmcp import FastMCP

from drive_auditor.config import ScanConfig
from drive_auditor.credentials import FileCredentialProvider
from drive_auditor.engine import human, largest_files_for_user as scan_one_user
from drive_auditor.jobs import InMemoryJobStore, start_scan as submit_scan
from drive_auditor.logging_setup import configure_logging

configure_logging()

mcp = FastMCP("google-workspace-steward")
_STORE = InMemoryJobStore()


def get_provider(tenant: str | None = None) -> FileCredentialProvider:
    """The single credential seam. Phase 1: local key from env.
    Phase 2: replace this body with a Secrets-Manager lookup by tenant."""
    key_file = os.environ.get("GWS_KEY_FILE")
    admin_email = os.environ.get("GWS_ADMIN_EMAIL")
    if not key_file or not admin_email:
        raise RuntimeError("Set GWS_KEY_FILE and GWS_ADMIN_EMAIL environment variables.")
    return FileCredentialProvider.from_file(key_file, admin_email)


@mcp.tool()
def start_scan(top_files_per_user: int = 25, top_files_overall: int = 500,
               include_suspended: bool = False) -> dict:
    """Start an org-wide scan. Returns a job_id immediately; poll with
    get_scan_status / get_scan_results."""
    config = ScanConfig(
        top_files_per_user=top_files_per_user,
        top_files_overall=top_files_overall,
        include_suspended=include_suspended,
    )
    provider = get_provider()
    job_id = submit_scan(provider, config, _STORE)
    return {"job_id": job_id, "status": "queued"}


@mcp.tool()
def get_scan_status(job_id: str) -> dict:
    """Check progress of a running scan."""
    job = _STORE.get(job_id)
    if job is None:
        return {"error": f"no job with id {job_id}"}
    done, total = job.progress
    return {"status": job.status, "progress": {"done": done, "total": total},
            "warnings": job.warnings, "error": job.error}


@mcp.tool()
def get_scan_results(job_id: str) -> dict:
    """Get the finished report. If not done yet, returns the current status."""
    job = _STORE.get(job_id)
    if job is None:
        return {"error": f"no job with id {job_id}"}
    if job.status != "done" or job.result is None:
        done, total = job.progress
        return {"status": job.status, "progress": {"done": done, "total": total},
                "error": job.error}
    data = asdict(job.result)
    data["total_size_human"] = human(job.result.total_bytes)
    data["status"] = "done"
    return data


@mcp.tool()
def largest_files_for_user(email: str, top_n: int = 25) -> dict:
    """Largest Drive files for ONE user (fast, runs synchronously)."""
    config = ScanConfig(top_files_per_user=top_n)
    provider = get_provider()
    result = scan_one_user(provider, email, config)
    for f in result.files:
        f["size_human"] = human(f["bytes"])
    return {"email": email, "count": len(result.files),
            "files": result.files, "error": result.error}


if __name__ == "__main__":
    mcp.run()
