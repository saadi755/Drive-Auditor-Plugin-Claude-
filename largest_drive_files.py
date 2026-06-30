#!/usr/bin/env python3
"""
largest_drive_files.py
----------------------
Thin command-line wrapper over the new engine — preserves the original
standalone-script use case for devs. It builds a FileCredentialProvider and a
ScanConfig from the command line / env, runs a full concurrent scan, writes a
CSV, and prints the top 20.

Usage:
    python largest_drive_files.py KEY.json admin@yourdomain.com
    python largest_drive_files.py KEY.json admin@yourdomain.com --csv out.csv

Or set GWS_KEY_FILE / GWS_ADMIN_EMAIL and omit the first two args.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from drive_auditor.config import ScanConfig
from drive_auditor.credentials import FileCredentialProvider
from drive_auditor.engine import human, scan_org
from drive_auditor.logging_setup import configure_logging


def main() -> None:
    p = argparse.ArgumentParser(description="Largest Drive files per user (org-wide).")
    p.add_argument("key_file", nargs="?", default=os.environ.get("GWS_KEY_FILE"))
    p.add_argument("admin_email", nargs="?", default=os.environ.get("GWS_ADMIN_EMAIL"))
    p.add_argument("--csv", default="largest_files.csv")
    p.add_argument("--per-user", type=int, default=25)
    p.add_argument("--overall", type=int, default=500)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--include-suspended", action="store_true")
    args = p.parse_args()

    if not args.key_file or not args.admin_email:
        p.error("provide KEY.json and admin@domain (or set GWS_KEY_FILE / GWS_ADMIN_EMAIL)")

    configure_logging()
    provider = FileCredentialProvider.from_file(args.key_file, args.admin_email)
    config = ScanConfig(
        top_files_per_user=args.per_user,
        top_files_overall=args.overall,
        max_workers=args.workers,
        include_suspended=args.include_suspended,
    )

    print("Scanning... (this can take a while on large orgs)")
    result = scan_org(provider, config,
                      progress=lambda d, t: print(f"  {d}/{t} users", end="\r"))
    print()

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Rank", "Owner", "File name", "Size", "Bytes",
                    "Type", "Modified", "File ID"])
        for rank, f in enumerate(result.results, 1):
            w.writerow([rank, f["owner"], f["name"], human(f["bytes"]),
                        f["bytes"], f["mimeType"], f["modified"], f["id"]])

    print(f"Done. {result.files_in_report} files written to {args.csv}")
    if result.warnings:
        print(f"({len(result.warnings)} user(s) had warnings — see logs)")
    print("\nTop 20 across the org:")
    for rank, f in enumerate(result.results[:20], 1):
        print(f"{rank:>3}. {human(f['bytes']):>10}  {f['owner']:<30} {f['name']}")


if __name__ == "__main__":
    main()
