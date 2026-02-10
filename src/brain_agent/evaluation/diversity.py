"""Diversity scoring helpers."""

from __future__ import annotations

from typing import Any

from ..config import DiversityPolicy


def diversity_bonus(payload: dict[str, Any], policy: DiversityPolicy) -> float:
    """Compute bonus score from diversity endpoint payload."""
    region_count = _count_unique(payload, "region")
    delay_count = _count_unique(payload, "delay")
    category_count = _count_unique(payload, "dataCategory")

    region_score = min(region_count / max(policy.target_regions, 1), 1.0)
    delay_score = min(delay_count / max(policy.target_delays, 1), 1.0)
    category_score = min(category_count / max(policy.target_data_categories, 1), 1.0)

    avg = (region_score + delay_score + category_score) / 3.0
    return avg * policy.diversity_bonus_weight


def blended_final_score(alpha_score: float, diversity_bonus_value: float) -> float:
    """Combine alpha quality score and diversity bonus."""
    return alpha_score + diversity_bonus_value


def _count_unique(payload: dict[str, Any], key: str) -> int:
    records = payload.get("records", [])
    if not isinstance(records, list):
        return 0
    values = {str(row.get(key)) for row in records if isinstance(row, dict) and row.get(key) is not None}
    return len(values)
