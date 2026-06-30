[drive-storage-auditor-README.md](https://github.com/user-attachments/files/29497619/drive-storage-auditor-README.md)
# Drive Storage Auditor

A read-only tool that scans a Google Workspace organization and finds the
**largest Google Drive files across all users** — built to help admins see what
is consuming their pooled storage quota. It runs both as a standalone CLI and as
an MCP server (a tool an AI assistant like Claude can call).

> Read-only by design: it requests only Drive **metadata** scopes and never
> reads file contents.

## Features

- Scans every user in a Workspace org and ranks the biggest files org-wide.
- **Concurrent** per-user scanning with a thread pool.
- **Retry with exponential backoff + jitter** on rate limits (429) and server
  errors (5xx); fatal errors (bad scope/auth) surface instead of being hidden.
- **Async job model** — `start_scan` returns a job ID immediately and the scan
  runs in the background (so it survives long scans without timing out).
- Clean separation of concerns: config, credentials, retry, engine, jobs, and
  logging are independent modules with no global state.
- JSON structured logging to stderr.
- Unit tested (no network needed — uses fakes).

## How it works

The tool uses a Google Cloud **service account with domain-wide delegation**: it
impersonates a Workspace admin to list users, then impersonates each user to
read their Drive file metadata. This is the standard pattern for org-wide,
admin-level Drive access.

## Project layout

```
src/drive_auditor/
  config.py         # ScanConfig dataclass — immutable, no globals
  credentials.py    # CredentialProvider — builds impersonating SA credentials
  backoff.py        # with_retry — exponential backoff + jitter
  engine.py         # scan_org — concurrent scan, aggregation, warnings
  jobs.py           # JobStore + InMemoryJobStore + start_scan
  logging_setup.py  # JSON logging to stderr
mcp_server.py       # MCP tools: start_scan / get_scan_status / get_scan_results
largest_drive_files.py  # standalone CLI over the same engine
test_auth.py        # quick credential check
tests/              # unit tests (pytest)
```

## Setup

### 1. Google Cloud / Workspace (one-time)

1. In Google Cloud Console, enable the **Admin SDK API** and **Google Drive API**.
2. Create a **service account** and download its JSON key.
3. In the Google **Admin Console** → Security → API controls → **Domain-wide
   delegation**, authorize the service account's Client ID with these read-only
   scopes:
   ```
   https://www.googleapis.com/auth/admin.directory.user.readonly,
   https://www.googleapis.com/auth/drive.metadata.readonly
   ```

> Keep the JSON key private. It is git-ignored here and should never be
> committed.

### 2. Install

```bash
pip install -r requirements.txt
```

## Usage

### Verify credentials

```bash
python test_auth.py path/to/key.json admin@yourdomain.com
```

### Run a full scan (CLI)

```bash
python largest_drive_files.py path/to/key.json admin@yourdomain.com --csv report.csv
```

### Run the tests (no credentials needed)

```bash
python -m pytest tests/ -v
```

### Run as an MCP server

```bash
export GWS_KEY_FILE=path/to/key.json
export GWS_ADMIN_EMAIL=admin@yourdomain.com
python mcp_server.py
```

Tools exposed: `start_scan`, `get_scan_status`, `get_scan_results`,
`largest_files_for_user`.

## Notes & limitations

- Ranks by `quotaBytesUsed` (the value that counts against storage), so native
  Google Docs/Sheets (which report ~0) don't dominate the list.
- Scans **My Drive** per user; Shared Drive files (org-owned) are out of scope.

## License

MIT — see `LICENSE`.
