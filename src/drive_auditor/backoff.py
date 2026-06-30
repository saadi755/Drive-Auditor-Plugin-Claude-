"""
backoff.py
==========
Retry helper for Google API calls. Wrap every .execute() in with_retry so that
transient throttling (429) and server hiccups (5xx) are retried with exponential
backoff + full jitter — instead of the old code's silent "except -> []" that
dropped throttled users.

Fatal errors (403 insufficient scope, 401 bad delegation, 404) are NOT retried;
they surface immediately so the caller can record a real failure.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from googleapiclient.errors import HttpError

T = TypeVar("T")

# Transient: worth retrying.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        return getattr(exc.resp, "status", None) in RETRYABLE_STATUS
    # Network-level blips.
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return False


def with_retry(fn: Callable[[], T], *, max_retries: int,
               base: float = 0.5, cap: float = 30.0) -> T:
    """Call fn(); retry on transient errors with exponential backoff + jitter.

    Args:
        fn:          a zero-argument callable, e.g. lambda: request.execute()
        max_retries: how many times to retry AFTER the first attempt.
        base:        base backoff seconds (pass 0 in tests to skip sleeping).
        cap:         maximum backoff seconds per attempt.

    Re-raises the original exception on a non-retryable error or after the
    final attempt.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            if not _is_retryable(exc) or attempt > max_retries:
                raise
            ceiling = min(cap, base * (2 ** (attempt - 1)))
            time.sleep(random.uniform(0, ceiling))  # full jitter
