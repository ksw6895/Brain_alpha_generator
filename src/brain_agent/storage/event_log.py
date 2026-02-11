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
    normalized = dict(payload or {})
    normalized.setdefault("event_type", event_type)
    normalized.setdefault("run_id", str(normalized.get("run_id") or "legacy-run"))
    normalized.setdefault("idea_id", str(normalized.get("idea_id") or "unknown"))
    normalized.setdefault("stage", str(normalized.get("stage") or "legacy"))
    normalized.setdefault("message", str(normalized.get("message") or event_type))
    level = str(normalized.get("severity") or "info").lower()
    normalized["severity"] = level if level in {"info", "warn", "error"} else "info"
    normalized.setdefault("created_at", utc_now_iso())
    if not isinstance(normalized.get("payload"), dict):
        normalized["payload"] = {}

    row = {
        "event_type": event_type,
        "created_at": normalized["created_at"],
        "payload": normalized,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
