"""Filesystem helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_parent(path: Path) -> None:
    """Create parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with UTF-8 and stable formatting."""
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def utc_date() -> str:
    """Return current UTC date as YYYYMMDD."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")
