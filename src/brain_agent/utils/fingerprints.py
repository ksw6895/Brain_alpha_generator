"""Fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Return deterministic JSON string for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    """Hash text with sha256."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_settings_expression(settings: dict[str, Any], expression: str) -> str:
    """Compute canonical fingerprint for a simulation candidate."""
    raw = f"{canonical_json(settings)}::{expression.strip()}"
    return sha256_text(raw)
