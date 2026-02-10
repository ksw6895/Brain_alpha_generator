"""JSONL event logging helper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..constants import DEFAULT_EVENTS_PATH
from ..utils.filesystem import ensure_parent, utc_now_iso


def append_event(event_type: str, payload: dict[str, Any], path: str | Path = DEFAULT_EVENTS_PATH) -> None:
    """Append one event to JSONL file."""
    p = Path(path)
    ensure_parent(p)
    row = {
        "event_type": event_type,
        "created_at": utc_now_iso(),
        "payload": payload,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
