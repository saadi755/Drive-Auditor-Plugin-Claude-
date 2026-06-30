#!/usr/bin/env python3
"""
test_auth.py
------------
Staged check that the service-account key, domain-wide delegation, and scopes
work — WITHOUT scanning the whole org. Now built on CredentialProvider, so it
takes the key + admin from the command line or env vars (no CONFIG to edit).

Usage:
    python test_auth.py KEY.json admin@yourdomain.com
    python test_auth.py KEY.json admin@yourdomain.com someone@yourdomain.com

Or via environment variables:
    GWS_KEY_FILE=KEY.json GWS_ADMIN_EMAIL=admin@yourdomain.com python test_auth.py
"""

from __future__ import annotations

import os
import sys

# Make the src/ package importable when run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from drive_auditor.credentials import FileCredentialProvider


def _human(n: int) -> str:
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def check_key_file(path: str) -> bool:
    print("1) Key file...")
    if not os.path.exists(path):
        print(f"   FAIL: key file '{path}' not found.")
        return False
    print(f"   OK: found '{path}'")
    return True


def check_list_users(provider) -> list[str] | None:
    print("2) Listing users (tests admin impersonation + directory scope)...")
    try:
        service = provider.directory_service()
        users, page_token = [], None
        while True:
            resp = service.users().list(
                customer="my_customer", maxResults=500,
                orderBy="email", pageToken=page_token, projection="basic",
            ).execute()
            users.extend(u["primaryEmail"] for u in resp.get("users", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:  # noqa: BLE001
        print(f"   FAIL: {e}")
        print("   -> Usually delegation not authorized, wrong admin, or API not enabled.")
        return None
    print(f"   OK: found {len(users)} user(s). First few:")
    for u in users[:5]:
        print(f"      - {u}")
    return users


def check_one_user(provider, email: str) -> bool:
    print(f"3) Scanning Drive for ONE user ({email})...")
    try:
        service = provider.drive_service(email)
        resp = service.files().list(
            q="'me' in owners and trashed = false",
            orderBy="quotaBytesUsed desc", pageSize=5, corpora="user",
            fields="files(name,quotaBytesUsed)",
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"   FAIL: {e}")
        return False
    files = resp.get("files", [])
    if not files:
        print("   OK (call succeeded) but this user has no files / none returned.")
        return True
    print(f"   OK: top {len(files)} file(s):")
    for f in files:
        size = int(f.get("quotaBytesUsed", "0"))
        print(f"      {_human(size):>10}  {f.get('name', '')}")
    return True


def main() -> None:
    args = sys.argv[1:]
    key_file = args[0] if len(args) > 0 else os.environ.get("GWS_KEY_FILE", "")
    admin_email = args[1] if len(args) > 1 else os.environ.get("GWS_ADMIN_EMAIL", "")

    if not key_file or not admin_email:
        sys.exit("Usage: python test_auth.py KEY.json admin@yourdomain.com [user@yourdomain.com]\n"
                 "   or set GWS_KEY_FILE and GWS_ADMIN_EMAIL env vars.")

    print(f"Using KEY_FILE={key_file}  ADMIN_EMAIL={admin_email}\n")
    if not check_key_file(key_file):
        sys.exit(1)

    provider = FileCredentialProvider.from_file(key_file, admin_email)

    users = check_list_users(provider)
    if users is None:
        sys.exit(1)

    target = args[2] if len(args) > 2 else admin_email
    check_one_user(provider, target)

    print("\nAll basic checks passed. The credentials are working.")


if __name__ == "__main__":
    main()
