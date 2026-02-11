"""LLM prompt helpers and strict parser contracts for 2-agent generation."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable, Literal, TypeVar

from pydantic import ValidationError

from ..retrieval.pack_builder import RetrievalPack
from ..schemas import CandidateAlpha, IdeaSpec, SimulationTarget

ParseErrorCode = Literal[
    "empty_output",
    "json_decode_error",
    "payload_not_object",
    "schema_validation_error",
    "contract_violation",
]

T = TypeVar("T")


class ParseFailure(ValueError):
    """Strict parse failure with standardized stage/code metadata."""

    def __init__(self, *, stage: str, code: ParseErrorCode, detail: str) -> None:
        self.stage = stage
        self.code = code
        self.detail = detail
        super().__init__(f"[{stage}:{code}] {detail}")


def build_idea_researcher_prompt(
    *,
    category: str | None,
    subcategory: str | None,
    target: SimulationTarget | dict[str, Any] | None,
    overview: str | None = None,
    recent_performance_summary: str | None = None,
    rules: list[str] | None = None,
) -> str:
    """Build Idea Researcher prompt contract payload (JSON envelope)."""
    target_payload: dict[str, Any]
    if isinstance(target, SimulationTarget):
        target_payload = target.model_dump(mode="python")
    elif isinstance(target, dict):
        target_payload = target
    else:
        target_payload = SimulationTarget().model_dump(mode="python")

    base_rules = [
        "Return JSON only.",
        "Follow IdeaSpec schema exactly.",
        "Keep hypothesis as one concise sentence.",
        "keywords_for_retrieval should be practical query tokens.",
    ]
    if rules:
        base_rules.extend(rules)

    payload = {
        "agent": "Idea Researcher",
        "input": {
            "category": category,
            "subcategory": subcategory,
            "overview": overview,
            "recent_performance_summary": recent_performance_summary,
            "target": target_payload,
        },
        "rules": base_rules,
        "output_schema": {
            "idea_id": "str",
            "hypothesis": "str",
            "keywords_for_retrieval": ["str"],
            "target": "SimulationTarget object",
            "candidate_subcategories": ["str"],
            "exploration_intent": "optional str",
            "retrieval_context_id": "optional str",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_alpha_maker_prompt(
    idea: IdeaSpec,
    retrieval_pack: RetrievalPack,
    *,
    knowledge_pack: dict[str, Any] | None = None,
    rules: list[str] | None = None,
) -> str:
    """Build Alpha Maker prompt contract payload (JSON envelope)."""
    if not retrieval_pack.context_guard.full_metadata_blocked:
        raise ValueError("Retrieval pack does not satisfy full-metadata blocking guard")

    base_rules = [
        "Return JSON only.",
        "Follow CandidateAlpha schema exactly.",
        "simulation_settings.type must be REGULAR.",
        "simulation_settings.settings.language must be FASTEXPR.",
        "Use only retrieval_pack candidate fields/operators.",
    ]
    if rules:
        base_rules.extend(rules)

    payload = {
        "agent": "Alpha Maker",
        "idea": idea.model_dump(mode="python"),
        "retrieval_pack": _retrieval_prompt_payload(retrieval_pack),
        "knowledge_pack": knowledge_pack or {},
        "rules": base_rules,
        "output_schema": {
            "idea_id": "str",
            "alpha_id": None,
            "simulation_settings": {
                "type": "REGULAR",
                "settings": "SimulationSettings object (language=FASTEXPR)",
                "regular": "FastExpr string",
            },
            "generation_notes": {
                "used_fields": ["field id"],
                "used_operators": ["operator name"],
                "candidate_lane": "optional exploit|explore",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_fastexpr_prompt(
    idea: IdeaSpec,
    *,
    operators: list[dict[str, Any]],
    data_fields: list[dict[str, Any]],
    rules: list[str] | None = None,
) -> str:
    """Backward-compatible builder for step-16/17 call sites."""
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
                "candidate_lane": "optional exploit|explore",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_gated_fastexpr_prompt(
    idea: IdeaSpec,
    retrieval_pack: RetrievalPack,
    *,
    rules: list[str] | None = None,
) -> str:
    """Backward-compatible gated builder from retrieval pack only."""
    return build_alpha_maker_prompt(
        idea,
        retrieval_pack,
        rules=rules,
        knowledge_pack=None,
    )


def parse_idea_spec(raw_json: str) -> IdeaSpec:
    """Strict parse for IdeaSpec payload."""
    return _parse_model_payload(raw_json, stage="idea", model_parser=IdeaSpec.model_validate)


def parse_candidate_alpha(raw_json: str) -> CandidateAlpha:
    """Strict parse for CandidateAlpha payload + step-19 contract checks."""
    alpha = _parse_model_payload(raw_json, stage="alpha", model_parser=CandidateAlpha.model_validate)

    sim = alpha.simulation_settings
    if sim.type != "REGULAR":
        raise ParseFailure(
            stage="alpha",
            code="contract_violation",
            detail="simulation_settings.type must be REGULAR",
        )
    language = str(sim.settings.language or "").upper()
    if language != "FASTEXPR":
        raise ParseFailure(
            stage="alpha",
            code="contract_violation",
            detail="simulation_settings.settings.language must be FASTEXPR",
        )
    if not (sim.regular or "").strip():
        raise ParseFailure(
            stage="alpha",
            code="contract_violation",
            detail="simulation_settings.regular must be a non-empty FastExpr string",
        )
    return alpha


def parse_with_format_repair(
    raw_text: str,
    *,
    parser: Callable[[str], T],
) -> tuple[T, bool]:
    """Try strict parse first, then one JSON-format repair pass."""
    try:
        return parser(raw_text), False
    except ParseFailure:
        repaired = repair_json_text(raw_text)
        if repaired.strip() == raw_text.strip():
            raise
        return parser(repaired), True


def repair_json_text(raw_text: str) -> str:
    """Attempt best-effort JSON formatting repair without semantic edits."""
    if not str(raw_text or "").strip():
        raise ParseFailure(stage="repair", code="empty_output", detail="Model output is empty")

    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(text: str | None) -> None:
        if text is None:
            return
        value = text.strip()
        if not value or value in seen:
            return
        seen.add(value)
        candidates.append(value)

    cleaned = str(raw_text)
    add_candidate(cleaned)

    fenced = _strip_markdown_fence(cleaned)
    add_candidate(fenced)

    fragment = _extract_json_fragment(cleaned)
    add_candidate(fragment)

    if fenced:
        add_candidate(_extract_json_fragment(fenced))

    for text in list(candidates):
        add_candidate(_remove_trailing_commas(text))

    for text in list(candidates):
        normalized = _normalize_pythonish_literals(text)
        add_candidate(normalized)
        add_candidate(_remove_trailing_commas(normalized))

    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            continue

    for candidate in candidates:
        try:
            literal = ast.literal_eval(candidate)
            return json.dumps(literal, ensure_ascii=False)
        except Exception:
            continue

    raise ParseFailure(
        stage="repair",
        code="json_decode_error",
        detail="Failed to repair JSON format from model output",
    )


def _parse_model_payload(
    raw_json: str,
    *,
    stage: str,
    model_parser: Callable[[dict[str, Any]], T],
) -> T:
    text = str(raw_json or "").strip()
    if not text:
        raise ParseFailure(stage=stage, code="empty_output", detail="Model output is empty")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseFailure(
            stage=stage,
            code="json_decode_error",
            detail=f"{exc.msg} (line={exc.lineno}, col={exc.colno})",
        ) from exc

    if not isinstance(payload, dict):
        raise ParseFailure(
            stage=stage,
            code="payload_not_object",
            detail="Top-level JSON payload must be an object",
        )

    try:
        return model_parser(payload)
    except ValidationError as exc:
        excerpt = "; ".join(str(err.get("msg", "validation_error")) for err in exc.errors()[:3])
        raise ParseFailure(
            stage=stage,
            code="schema_validation_error",
            detail=excerpt or "schema validation failed",
        ) from exc


def _retrieval_prompt_payload(retrieval_pack: RetrievalPack) -> dict[str, Any]:
    return {
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


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped

    # Drop opening fence and optional language tag.
    lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_fragment(text: str) -> str | None:
    src = text.strip()
    if not src:
        return None

    first_obj = src.find("{")
    first_arr = src.find("[")
    start_candidates = [idx for idx in (first_obj, first_arr) if idx != -1]
    if not start_candidates:
        return None

    start = min(start_candidates)
    opener = src[start]
    closer = "}" if opener == "{" else "]"

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(src)):
        ch = src[idx]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == opener:
            depth += 1
            continue
        if ch == closer:
            depth -= 1
            if depth == 0:
                return src[start : idx + 1]
    return None


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _normalize_pythonish_literals(text: str) -> str:
    out = re.sub(r"\bNone\b", "null", text)
    out = re.sub(r"\bTrue\b", "true", out)
    out = re.sub(r"\bFalse\b", "false", out)
    return out
