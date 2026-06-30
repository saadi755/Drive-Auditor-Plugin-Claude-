#!/usr/bin/env python3
"""
check_setup.py
--------------
A simple "does everything load correctly?" check. It does NOT contact Google
and needs no credentials. Just run it:

    python check_setup.py

If you see "ALL GOOD" at the end, the code is wired up correctly.
"""

import os
import sys

# Find the src/ folder next to this file, no matter where you run it from.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

print("Checking the four modules load...\n")

try:
    from drive_auditor.config import ScanConfig
    from drive_auditor.logging_setup import configure_logging, get_logger
    from drive_auditor.credentials import FileCredentialProvider, SCOPES
except ModuleNotFoundError as e:
    print(f"PROBLEM: a library is missing -> {e}")
    print("Fix: run this first ->  pip install google-api-python-client google-auth")
    sys.exit(1)
except ImportError as e:
    print(f"PROBLEM: could not find the drive_auditor files -> {e}")
    print("Fix: run this file from the 'steward' folder that contains the 'src' folder.")
    sys.exit(1)

print("  - config.py        loaded")
print("  - logging_setup.py loaded")
print("  - credentials.py   loaded")

cfg = ScanConfig()
print(f"\nDefault settings: {cfg}")
print(f"Read-only scopes: {SCOPES}")

configure_logging()
get_logger("check_setup", tenant_id="demo").info("logging works")

print("\nALL GOOD — the code is set up correctly.")
print("Next step (needs the key from your boss): python test_auth.py KEY.json admin@thetestorg.com")
