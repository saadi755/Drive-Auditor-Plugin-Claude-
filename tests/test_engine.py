"""Tests for engine.scan_org — uses a fake provider, no Google calls.

Verifies: concurrent aggregation, sorting, top-N truncation, that a failing
user becomes a warning (not silently dropped), and that two configs don't
interfere (no global state)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from drive_auditor.config import ScanConfig
from drive_auditor.engine import scan_org


class FakeFiles:
    def __init__(self, files):
        self._files = files
    def list(self, **kwargs):
        return self
    def execute(self):
        return {"files": self._files}


class FakeUsers:
    def __init__(self, emails):
        self._emails = emails
    def list(self, **kwargs):
        return self
    def execute(self):
        return {"users": [{"primaryEmail": e, "suspended": False} for e in self._emails]}


class FakeDirService:
    def __init__(self, emails):
        self._emails = emails
    def users(self):
        return FakeUsers(self._emails)


class FakeDriveService:
    def __init__(self, files):
        self._files = files
    def files(self):
        return FakeFiles(self._files)


class FakeProvider:
    """Returns canned users and per-user files; one user is set to fail."""
    def __init__(self, user_files, failing=None):
        self.user_files = user_files          # {email: [file dicts]}
        self.failing = failing or set()

    def directory_service(self):
        return FakeDirService(list(self.user_files.keys()))

    def drive_service(self, email):
        if email in self.failing:
            raise RuntimeError("boom")        # simulate a hard failure
        files = [
            {"name": f["name"], "quotaBytesUsed": str(f["bytes"]),
             "mimeType": "application/octet-stream", "modifiedTime": "", "id": f["name"]}
            for f in self.user_files[email]
        ]
        return FakeDriveService(files)


def _provider():
    return FakeProvider(
        user_files={
            "alice@x.com": [{"name": "big.mov", "bytes": 5000}],
            "bob@x.com":   [{"name": "mid.zip", "bytes": 3000}],
            "carol@x.com": [{"name": "small.pdf", "bytes": 1000}],
        },
        failing={"carol@x.com"},
    )


def test_aggregates_and_sorts():
    res = scan_org(_provider(), ScanConfig(max_workers=3))
    assert res.users_scanned == 3
    # carol failed -> warning, not in results
    assert any("carol@x.com" in w for w in res.warnings)
    names = [f["name"] for f in res.results]
    assert names == ["big.mov", "mid.zip"]        # sorted desc, carol dropped to warning
    assert res.total_bytes == 8000


def test_top_overall_truncation():
    res = scan_org(_provider(), ScanConfig(max_workers=3, top_files_overall=1))
    assert res.files_in_report == 1
    assert res.results[0]["name"] == "big.mov"    # only the single biggest


def test_configs_do_not_interfere():
    # Two scans with different settings, back to back; results stay independent.
    a = scan_org(_provider(), ScanConfig(top_files_overall=1))
    b = scan_org(_provider(), ScanConfig(top_files_overall=5))
    assert a.files_in_report == 1
    assert b.files_in_report == 2                 # only 2 successful users have files
