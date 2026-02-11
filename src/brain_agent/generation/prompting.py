"""LLM prompt helpers for FastExpr builder."""

from __future__ import annotations

import json
from typing import Any

from ..retrieval.pack_builder import RetrievalPack
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


def build_gated_fastexpr_prompt(
    idea: IdeaSpec,
    retrieval_pack: RetrievalPack,
    *,
    rules: list[str] | None = None,
) -> str:
    """Build prompt from retrieval pack only (full metadata is blocked)."""
    if not retrieval_pack.context_guard.full_metadata_blocked:
        raise ValueError("Retrieval pack does not satisfy full-metadata blocking guard")

    base_rules = [
        "Return JSON only.",
        "Follow CandidateAlpha schema exactly.",
        "Use only candidate_operators and candidate_fields from retrieval_pack.",
        "Do not use operators/data fields outside retrieval_pack candidates.",
        "Expression must be type=REGULAR and language=FASTEXPR.",
    ]
    if rules:
        base_rules.extend(rules)

    retrieval_payload = {
        "idea_id": retrieval_pack.idea_id,
        "query": retrieval_pack.query,
        "target": retrieval_pack.target.model_dump(mode="python"),
        "selected_subcategories": retrieval_pack.selected_subcategories,
        "candidate_datasets": [x.model_dump(mode="python") for x in retrieval_pack.candidate_datasets],
        "candidate_fields": [x.model_dump(mode="python") for x in retrieval_pack.candidate_fields],
        "candidate_operators": [x.model_dump(mode="python") for x in retrieval_pack.candidate_operators],
        "lanes": {k: v.model_dump(mode="python") for k, v in retrieval_pack.lanes.items()},
        "budget_policy": retrieval_pack.budget_policy,
        "expansion_policy": retrieval_pack.expansion_policy,
        "context_guard": retrieval_pack.context_guard.model_dump(mode="python"),
    }

    payload = {
        "idea": idea.model_dump(mode="python"),
        "retrieval_pack": retrieval_payload,
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
