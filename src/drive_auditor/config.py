"""
config.py
=========
Per-request scan settings, passed explicitly through the engine instead of
living in module globals. Frozen so it is immutable and safe to share across
threads — this is what replaces the old CONFIG block in largest_drive_files.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanConfig:
    """Immutable settings for a single scan request.

    A fresh instance is built per request (per MCP tool call), so two tenants
    or two concurrent scans never share or mutate the same configuration.
    """

    top_files_per_user: int = 25   # biggest N files pulled per user
    top_files_overall: int = 500   # size of the final combined report
    include_suspended: bool = False
    max_workers: int = 8           # concurrent per-user Drive scans
    max_retries: int = 5           # retry attempts on throttling / 5xx

    def __post_init__(self) -> None:
        # Cheap guards so bad input fails loudly at construction, not mid-scan.
        if self.top_files_per_user < 1:
            raise ValueError("top_files_per_user must be >= 1")
        if self.top_files_overall < 1:
            raise ValueError("top_files_overall must be >= 1")
        if self.max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
