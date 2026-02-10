"""Diversity endpoint wrappers."""

from __future__ import annotations

from typing import Any

from .client import BrainAPISession


def get_diversity(
    session: BrainAPISession,
    user_id: str = "self",
    grouping: str = "region,delay,dataCategory",
) -> dict[str, Any]:
    """Fetch diversity activity snapshot."""
    r = session.get(f"/users/{user_id}/activities/diversity", params={"grouping": grouping})
    if r.status_code // 100 != 2:
        raise RuntimeError(f"diversity endpoint failed: {r.status_code} {r.text}")
    return r.json()
