"""
logging_setup.py
================
Structured logging to **stderr**, never stdout. The stdio MCP transport uses
stdout to talk to Claude, so any stray print() corrupts the channel — this
module is what replaces every print() in the old script.

Usage:
    from drive_auditor.logging_setup import configure_logging, get_logger

    configure_logging()                      # once, at process start
    log = get_logger(__name__, tenant_id="acme", job_id="abc123")
    log.info("scan started", extra={"request_id": "req-1"})
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line with tenant/job/request context."""

    # Fields we always try to include if present on the record.
    CONTEXT_FIELDS = ("tenant_id", "job_id", "request_id")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger to write JSON lines to stderr. Call once."""
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()      # avoid duplicate handlers on re-import
    root.addHandler(handler)
    root.setLevel(level)


class _ContextAdapter(logging.LoggerAdapter):
    """Injects tenant_id / job_id / request_id into every record."""

    def process(self, msg, kwargs):
        extra = dict(self.extra or {})
        extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, **context: Any) -> logging.LoggerAdapter:
    """Return a logger that stamps the given context onto each line.

    Example: get_logger(__name__, tenant_id="acme", job_id="abc123")
    """
    return _ContextAdapter(logging.getLogger(name), context)
