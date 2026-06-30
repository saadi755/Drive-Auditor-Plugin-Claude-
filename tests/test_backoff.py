"""Tests for backoff.with_retry — no network, uses fake exceptions."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest
from googleapiclient.errors import HttpError

from drive_auditor.backoff import with_retry


class FakeResp:
    """Minimal stand-in for an httplib2 response (HttpError reads .status/.reason)."""
    def __init__(self, status):
        self.status = status
        self.reason = "fake"


def _http_error(status):
    return HttpError(resp=FakeResp(status), content=b"{}")


def test_retries_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] <= 2:           # fail with 429 twice
            raise _http_error(429)
        return "ok"                   # then succeed

    # base=0 so the test doesn't actually sleep.
    result = with_retry(flaky, max_retries=5, base=0.0)
    assert result == "ok"
    assert calls["n"] == 3            # 2 failures + 1 success


def test_fatal_error_not_retried():
    calls = {"n": 0}

    def forbidden():
        calls["n"] += 1
        raise _http_error(403)        # insufficient scope = fatal

    with pytest.raises(HttpError):
        with_retry(forbidden, max_retries=5, base=0.0)
    assert calls["n"] == 1            # tried once, did NOT retry


def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def always_429():
        calls["n"] += 1
        raise _http_error(429)

    with pytest.raises(HttpError):
        with_retry(always_429, max_retries=3, base=0.0)
    assert calls["n"] == 4            # 1 initial + 3 retries
