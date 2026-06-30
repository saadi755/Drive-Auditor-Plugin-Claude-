"""
jobs.py
=======
Async job model so a full-org scan returns a job_id immediately instead of
blocking past the MCP tool timeout. The scan runs on a background thread; the
caller polls status/results.

JobStore is an interface on purpose: Phase 2 implements DynamoJobStore + an SQS
worker with this same surface, and neither the engine nor the tools change.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .config import ScanConfig
from .engine import ScanResult, scan_org
from .logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class ScanJob:
    id: str
    status: str = "queued"               # queued | running | done | failed
    progress: tuple[int, int] = (0, 0)   # (done, total)
    result: Optional[ScanResult] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


class JobStore(Protocol):
    def create(self) -> ScanJob: ...
    def get(self, job_id: str) -> Optional[ScanJob]: ...
    def update(self, job: ScanJob) -> None: ...


class InMemoryJobStore:
    """Phase 1 store: a dict guarded by a lock. Phase 2 swaps in DynamoJobStore."""

    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()

    def create(self) -> ScanJob:
        job = ScanJob(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[ScanJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: ScanJob) -> None:
        with self._lock:
            self._jobs[job.id] = job


# A shared executor for running scans in the background (Phase 1).
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def start_scan(provider, config: ScanConfig, store: JobStore,
               *, executor: ThreadPoolExecutor = _EXECUTOR) -> str:
    """Create a job, kick off the scan on a background thread, return job_id now."""
    job = store.create()

    def _run() -> None:
        job.status = "running"
        store.update(job)
        try:
            def _progress(done: int, total: int) -> None:
                job.progress = (done, total)
                store.update(job)

            result = scan_org(provider, config, progress=_progress)
            job.result = result
            job.warnings = result.warnings
            job.status = "done"
            store.update(job)
        except Exception as e:  # noqa: BLE001
            job.error = str(e)
            job.status = "failed"
            store.update(job)
            log.error("scan job failed", extra={"job_id": job.id})

    executor.submit(_run)
    return job.id
