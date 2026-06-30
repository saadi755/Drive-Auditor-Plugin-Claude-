"""
credentials.py
==============
Builds impersonating service-account credentials from **in-memory key material**
(a dict), not a hardcoded file path. This is what replaces the KEY_FILE/global
approach in the old largest_drive_files.py.

Why in-memory: each tenant gets its own provider instance built from its own
key. In Phase 1 the key comes from a local JSON file (FileCredentialProvider);
in Phase 2 the exact same CredentialProvider is fed key bytes straight from AWS
Secrets Manager — no engine change.

Thread-safety note: googleapiclient's discovery build() returns a service that
is NOT safe to share across threads. So we build a fresh service on every call
(directory_service / drive_service) and let each worker thread own its own.
"""

from __future__ import annotations

import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

# Read-only scopes — never escalate beyond metadata.
SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


class CredentialProvider:
    """Builds delegated (impersonating) SA credentials from in-memory key info.

    Args:
        key_info:    the parsed service-account JSON as a dict (the contents of
                     the downloaded key file, already loaded).
        admin_email: a Workspace super admin, impersonated to enumerate users.
    """

    def __init__(self, key_info: dict, admin_email: str):
        if not isinstance(key_info, dict) or "client_email" not in key_info:
            raise ValueError("key_info must be a parsed service-account key dict")
        if not admin_email:
            raise ValueError("admin_email is required")
        self._key_info = key_info
        self.admin_email = admin_email

    def _credentials_for(self, subject: str):
        """SA credentials that impersonate `subject`, scoped read-only."""
        creds = service_account.Credentials.from_service_account_info(
            self._key_info, scopes=SCOPES
        )
        return creds.with_subject(subject)

    def directory_service(self):
        """Admin SDK Directory service, impersonating the admin (lists users)."""
        creds = self._credentials_for(self.admin_email)
        return build("admin", "directory_v1", credentials=creds,
                     cache_discovery=False)

    def drive_service(self, user_email: str):
        """Drive service impersonating a specific user (reads their Drive).

        Build this INSIDE the worker thread that uses it — services are not
        safe to share across threads.
        """
        creds = self._credentials_for(user_email)
        return build("drive", "v3", credentials=creds, cache_discovery=False)


class FileCredentialProvider(CredentialProvider):
    """Dev/CLI convenience: load the key_info from a JSON file on disk."""

    @classmethod
    def from_file(cls, path: str, admin_email: str) -> "FileCredentialProvider":
        with open(path, "r", encoding="utf-8") as fh:
            key_info = json.load(fh)
        return cls(key_info, admin_email)
