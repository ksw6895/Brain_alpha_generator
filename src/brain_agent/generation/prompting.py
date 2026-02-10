"""LLM prompt helpers for FastExpr builder."""

from __future__ import annotations

import json
from typing import Any

from ..schemas import CandidateAlpha, IdeaSpec


def build_fastexpr_prompt(
    idea: IdeaSpec,
    *,
    operators: list[dict[str, Any]],
    data_fields: list[dict[str, Any]],
    rules: list[str] | None = None,
) -> str:
    """Build constrained prompt for JSON-only CandidateAlpha output."""
    base_rules = [
        "Return JSON only.",
        "Follow CandidateAlpha schema exactly.",
        "Use only provided operators and data fields.",
        "Expression must be type=REGULAR and language=FASTEXPR.",
    ]
    if rules:
        base_rules.extend(rules)

    payload = {
        "idea": idea.model_dump(mode="python"),
        "operators": operators,
        "data_fields": data_fields,
        "rules": base_rules,
        "output_schema": {
            "idea_id": "str",
            "alpha_id": None,
            "simulation_settings": {
                "type": "REGULAR",
                "settings": "SimulationSettings object",
                "regular": "FastExpr string",
            },
            "generation_notes": {
                "used_fields": ["field id"],
                "used_operators": ["operator name"],
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_candidate_alpha(raw_json: str) -> CandidateAlpha:
    """Strictly parse model output into CandidateAlpha."""
    payload = json.loads(raw_json)
    return CandidateAlpha.model_validate(payload)
