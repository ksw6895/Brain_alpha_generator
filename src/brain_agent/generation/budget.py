"""Step-20 budget policy, fallback, and telemetry helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, Field, field_validator

from ..retrieval.pack_builder import (
    FieldCandidate,
    LaneSelection,
    OperatorCandidate,
    RetrievalPack,
    RetrievalTelemetry,
    RetrievalTokenEstimate,
)
from ..schemas import IdeaSpec
from ..utils.filesystem import utc_now_iso


class BudgetBlockedError(RuntimeError):
    """Raised when prompt generation is blocked by budget policy."""


class LLMBudgetConfig(BaseModel):
    """Budget policy for LLM generation + fallback behavior."""

    max_prompt_tokens: int = 12000
    max_completion_tokens: int = 1600
    max_tokens_per_batch: int = 52000
    max_tokens_per_day: int = 1500000
    fallback_topk_steps: list[float] = Field(default_factory=lambda: [0.85, 0.7, 0.55, 0.4])
    exploit_ratio: float = 0.7
    explore_ratio: float = 0.3
    min_explore_candidates_per_batch: int = 1
    expansion_reserve_tokens: int = 2500
    estimated_cost_per_1k_prompt_tokens: float = 0.0
    estimated_cost_per_1k_completion_tokens: float = 0.0

    @field_validator("fallback_topk_steps")
    @classmethod
    def _validate_fallback_steps(cls, value: list[float]) -> list[float]:
        cleaned: list[float] = []
        for raw in value or []:
            try:
                step = float(raw)
            except Exception:
                continue
            if step <= 0 or step >= 1:
                continue
            cleaned.append(step)
        if not cleaned:
            return [0.85, 0.7, 0.55, 0.4]
        return cleaned

    def normalized_lane_ratio(self) -> tuple[float, float]:
        exploit = max(0.0, float(self.exploit_ratio))
        explore = max(0.0, float(self.explore_ratio))
        total = exploit + explore
        if total <= 0:
            return 0.7, 0.3
        return exploit / total, explore / total


@dataclass
class UsageSnapshot:
    run_prompt_tokens: int = 0
    run_completion_tokens: int = 0
    day_prompt_tokens: int = 0
    day_completion_tokens: int = 0
    run_calls: int = 0
    day_calls: int = 0

    @property
    def total_run_tokens(self) -> int:
        return self.run_prompt_tokens + self.run_completion_tokens

    @property
    def total_day_tokens(self) -> int:
        return self.day_prompt_tokens + self.day_completion_tokens


@dataclass
class BudgetEvaluation:
    passed: bool
    prompt_tokens_rough: int
    completion_tokens_budget: int
    projected_batch_tokens: int
    projected_day_tokens: int
    selected_topk: dict[str, int]
    lane_ratio: dict[str, Any]
    coverage_kpi: float
    novelty_kpi: float
    combo_sample: list[str]
    explore_floor_preserved: bool
    exceeded: dict[str, bool]
    fallback_count: int
    estimated_request_cost_usd: float


@dataclass
class BudgetEnforcementResult:
    allowed: bool
    pack: RetrievalPack
    prompt: str
    evaluation: BudgetEvaluation
    usage: UsageSnapshot
    fallback_steps: list[dict[str, Any]] = field(default_factory=list)


def load_llm_budget(path: str | Path | None = None) -> LLMBudgetConfig:
    """Load LLM budget config from JSON; fall back to defaults when missing."""
    if path is None:
        return LLMBudgetConfig()

    p = Path(path)
    if not p.exists():
        return LLMBudgetConfig()

    payload = json.loads(p.read_text(encoding="utf-8"))
    return LLMBudgetConfig.model_validate(payload)


def rough_token_estimate(text_or_chars: str | int | None) -> int:
    """Conservative token estimate from character length."""
    if text_or_chars is None:
        return 0
    if isinstance(text_or_chars, int):
        chars = max(0, int(text_or_chars))
    else:
        chars = len(str(text_or_chars))
    return max(0, int(math.ceil(chars / 4.0)))


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, budget: LLMBudgetConfig) -> float:
    prompt_cost = (max(0, prompt_tokens) / 1000.0) * max(0.0, float(budget.estimated_cost_per_1k_prompt_tokens))
    completion_cost = (max(0, completion_tokens) / 1000.0) * max(
        0.0,
        float(budget.estimated_cost_per_1k_completion_tokens),
    )
    return float(prompt_cost + completion_cost)


def extract_prompt_completion_tokens(
    usage: dict[str, Any] | None,
    *,
    fallback_prompt: int = 0,
    fallback_completion: int = 0,
) -> tuple[int, int]:
    """Extract usage tokens from OpenAI payloads with rough fallback."""
    payload = usage if isinstance(usage, dict) else {}

    prompt = _first_nonneg_int(payload, ("prompt_tokens", "input_tokens", "input_token_count"))
    completion = _first_nonneg_int(payload, ("completion_tokens", "output_tokens", "output_token_count"))
    total = _first_nonneg_int(payload, ("total_tokens", "token_count"))

    if prompt <= 0:
        prompt = max(0, int(fallback_prompt))
    if completion <= 0:
        completion = max(0, int(fallback_completion))

    if total > 0 and completion <= 0 and prompt > 0:
        completion = max(0, total - prompt)
    if total > 0 and prompt <= 0 and completion > 0:
        prompt = max(0, total - completion)

    return prompt, completion


def aggregate_usage_from_events(
    events: Iterable[dict[str, Any]],
    *,
    run_id: str,
    utc_day: str | None = None,
) -> UsageSnapshot:
    """Aggregate run/day token usage from llm.usage_point events."""
    snapshot = UsageSnapshot()
    day = (utc_day or utc_now_iso()[:10]).strip()[:10]

    for event in events:
        if str(event.get("event_type") or "") != "llm.usage_point":
            continue

        detail = event.get("payload")
        payload = detail if isinstance(detail, dict) else {}

        usage = payload.get("usage")
        prompt_tokens, completion_tokens = extract_prompt_completion_tokens(
            usage if isinstance(usage, dict) else {},
            fallback_prompt=_to_int(payload.get("prompt_tokens_rough")),
            fallback_completion=_to_int(payload.get("completion_tokens_rough")),
        )

        event_run_id = str(event.get("run_id") or "")
        created_at = str(event.get("created_at") or "")

        if event_run_id == run_id:
            snapshot.run_prompt_tokens += prompt_tokens
            snapshot.run_completion_tokens += completion_tokens
            snapshot.run_calls += 1

        if created_at.startswith(day):
            snapshot.day_prompt_tokens += prompt_tokens
            snapshot.day_completion_tokens += completion_tokens
            snapshot.day_calls += 1

    return snapshot


def collect_seen_combinations(events: Iterable[dict[str, Any]], *, run_id: str) -> set[str]:
    """Collect previously logged field/operator combos for novelty KPI."""
    out: set[str] = set()
    for event in events:
        if str(event.get("run_id") or "") != run_id:
            continue
        if not str(event.get("event_type") or "").startswith("budget."):
            continue
        detail = event.get("payload")
        payload = detail if isinstance(detail, dict) else {}
        combos = payload.get("combo_sample")
        if not isinstance(combos, list):
            continue
        for value in combos:
            if isinstance(value, str) and value:
                out.add(value)
    return out


def can_use_expansion_reserve(
    *,
    repeated_error_count: int,
    estimated_extra_prompt_tokens: int,
    budget: LLMBudgetConfig,
    trigger_threshold: int = 2,
) -> bool:
    """Return whether reserved expansion budget can be used for repeated errors."""
    if repeated_error_count < max(1, trigger_threshold):
        return False
    return max(0, int(estimated_extra_prompt_tokens)) <= max(0, int(budget.expansion_reserve_tokens))


def compact_knowledge_bundle(
    knowledge_bundle: dict[str, Any],
    retrieval_pack: RetrievalPack,
    *,
    max_examples: int = 8,
) -> dict[str, Any]:
    """Project knowledge pack into retrieval-aware compact payload for prompt budget."""
    if not isinstance(knowledge_bundle, dict):
        return {}

    operator_names = {row.name for row in retrieval_pack.candidate_operators if row.name}
    field_ids = {row.id for row in retrieval_pack.candidate_fields if row.id}

    compact: dict[str, Any] = {}

    signature_pack = knowledge_bundle.get("operator_signature_pack")
    if isinstance(signature_pack, dict):
        operators = signature_pack.get("operators")
        keep_ops = []
        if isinstance(operators, list):
            for row in operators:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "")
                if not name or (operator_names and name not in operator_names):
                    continue
                keep_ops.append(row)
        compact["operator_signature_pack"] = {
            "version": signature_pack.get("version"),
            "generated_at": signature_pack.get("generated_at"),
            "operator_count": len(keep_ops),
            "operators": keep_ops,
        }

    examples_pack = knowledge_bundle.get("fastexpr_examples_pack")
    if isinstance(examples_pack, dict):
        examples = examples_pack.get("examples")
        keep_examples = []
        if isinstance(examples, list):
            for row in examples:
                if not isinstance(row, dict):
                    continue
                used_ops = {str(x) for x in row.get("used_operators", []) if str(x)}
                used_fields = {str(x) for x in row.get("used_fields", []) if str(x)}
                if operator_names and used_ops and used_ops.isdisjoint(operator_names) and used_fields.isdisjoint(field_ids):
                    continue
                keep_examples.append(row)
                if len(keep_examples) >= max(1, int(max_examples)):
                    break
        compact["fastexpr_examples_pack"] = {
            "version": examples_pack.get("version"),
            "generated_at": examples_pack.get("generated_at"),
            "fallback_used": bool(examples_pack.get("fallback_used", False)),
            "examples": keep_examples,
        }

    visual_pack = knowledge_bundle.get("fastexpr_visual_pack")
    if isinstance(visual_pack, dict):
        visual_ops = visual_pack.get("operators")
        keep_visual_ops = []
        if isinstance(visual_ops, list):
            for row in visual_ops:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "")
                if not name or (operator_names and name not in operator_names):
                    continue
                keep_visual_ops.append(row)

        example_cards = visual_pack.get("example_cards")
        keep_cards = []
        if isinstance(example_cards, list):
            for card in example_cards:
                if not isinstance(card, dict):
                    continue
                used_ops = {str(x) for x in card.get("used_operators", []) if str(x)}
                if operator_names and used_ops and used_ops.isdisjoint(operator_names):
                    continue
                keep_cards.append(card)
                if len(keep_cards) >= max(1, int(max_examples)):
                    break

        compact["fastexpr_visual_pack"] = {
            "version": visual_pack.get("version"),
            "generated_at": visual_pack.get("generated_at"),
            "operators": keep_visual_ops,
            "error_taxonomy": visual_pack.get("error_taxonomy") if isinstance(visual_pack.get("error_taxonomy"), list) else [],
            "example_cards": keep_cards,
        }

    settings_pack = knowledge_bundle.get("simulation_settings_allowed_pack")
    if isinstance(settings_pack, dict):
        compact["simulation_settings_allowed_pack"] = settings_pack

    compact["compact_policy"] = {
        "operator_candidates": len(operator_names),
        "field_candidates": len(field_ids),
        "max_examples": max(1, int(max_examples)),
    }
    return compact


def enforce_alpha_prompt_budget(
    *,
    idea: IdeaSpec,
    retrieval_pack: RetrievalPack,
    knowledge_bundle: dict[str, Any],
    budget: LLMBudgetConfig,
    usage: UsageSnapshot,
    seen_combo_keys: set[str],
    prompt_builder: Callable[[IdeaSpec, RetrievalPack, dict[str, Any]], str],
    max_output_tokens: int,
) -> BudgetEnforcementResult:
    """Apply request/batch/day budget checks with staged Top-K fallback."""
    working_pack = retrieval_pack.model_copy(deep=True)
    explore_floor_targets = _explore_floor_targets(retrieval_pack, budget)
    _sync_pack_contracts(working_pack, budget)

    prompt = prompt_builder(idea, working_pack, knowledge_bundle)
    fallback_count = 0
    evaluation = _evaluate_budget(
        prompt=prompt,
        pack=working_pack,
        budget=budget,
        usage=usage,
        seen_combo_keys=seen_combo_keys,
        max_output_tokens=max_output_tokens,
        fallback_count=fallback_count,
        explore_floor_targets=explore_floor_targets,
    )
    if evaluation.passed:
        return BudgetEnforcementResult(
            allowed=True,
            pack=working_pack,
            prompt=prompt,
            evaluation=evaluation,
            usage=usage,
        )

    fallback_steps: list[dict[str, Any]] = []
    for phase in ("fields", "operators", "subcategories"):
        for factor in budget.fallback_topk_steps:
            signature_before = _pack_signature(working_pack)
            _shrink_pack(working_pack, phase=phase, factor=factor, budget=budget)
            _sync_pack_contracts(working_pack, budget)
            signature_after = _pack_signature(working_pack)

            if signature_after == signature_before:
                continue

            fallback_count += 1
            prompt = prompt_builder(idea, working_pack, knowledge_bundle)
            evaluation = _evaluate_budget(
                prompt=prompt,
                pack=working_pack,
                budget=budget,
                usage=usage,
                seen_combo_keys=seen_combo_keys,
                max_output_tokens=max_output_tokens,
                fallback_count=fallback_count,
                explore_floor_targets=explore_floor_targets,
            )
            fallback_steps.append(
                {
                    "phase": phase,
                    "factor": round(float(factor), 4),
                    "prompt_tokens": evaluation.prompt_tokens_rough,
                    "completion_tokens": evaluation.completion_tokens_budget,
                    "selected_topk": evaluation.selected_topk,
                    "budget_exceeded": evaluation.exceeded,
                    "fallback_count": fallback_count,
                }
            )

            if evaluation.passed:
                return BudgetEnforcementResult(
                    allowed=True,
                    pack=working_pack,
                    prompt=prompt,
                    evaluation=evaluation,
                    usage=usage,
                    fallback_steps=fallback_steps,
                )

    return BudgetEnforcementResult(
        allowed=False,
        pack=working_pack,
        prompt=prompt,
        evaluation=evaluation,
        usage=usage,
        fallback_steps=fallback_steps,
    )


def build_budget_event_payload(
    *,
    step_name: str,
    budget: LLMBudgetConfig,
    usage: UsageSnapshot,
    evaluation: BudgetEvaluation,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalized payload for budget.* telemetry events."""
    payload: dict[str, Any] = {
        "step_name": step_name,
        "prompt_tokens": evaluation.prompt_tokens_rough,
        "completion_tokens": evaluation.completion_tokens_budget,
        "selected_topk": evaluation.selected_topk,
        "lane_ratio": evaluation.lane_ratio,
        "budget_exceeded": evaluation.exceeded,
        "fallback_count": evaluation.fallback_count,
        "coverage_kpi": evaluation.coverage_kpi,
        "novelty_kpi": evaluation.novelty_kpi,
        "combo_sample": evaluation.combo_sample,
        "projected_batch_tokens": evaluation.projected_batch_tokens,
        "projected_day_tokens": evaluation.projected_day_tokens,
        "batch_tokens_used_before": usage.total_run_tokens,
        "day_tokens_used_before": usage.total_day_tokens,
        "estimated_request_cost_usd": round(evaluation.estimated_request_cost_usd, 8),
        "explore_floor_preserved": evaluation.explore_floor_preserved,
        "limits": {
            "max_prompt_tokens": budget.max_prompt_tokens,
            "max_completion_tokens": budget.max_completion_tokens,
            "max_tokens_per_batch": budget.max_tokens_per_batch,
            "max_tokens_per_day": budget.max_tokens_per_day,
            "min_explore_candidates_per_batch": budget.min_explore_candidates_per_batch,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def build_budget_console_payload(
    *,
    run_id: str,
    run_events: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    budget: LLMBudgetConfig,
) -> dict[str, Any]:
    """Build chart-friendly payload for Budget Console endpoint."""
    usage = aggregate_usage_from_events(all_events, run_id=run_id)

    prompt_series: list[dict[str, Any]] = []
    completion_series: list[dict[str, Any]] = []
    fallback_timeline: list[dict[str, Any]] = []
    latest_payload: dict[str, Any] = {}

    flags = {
        "budget_blocked": False,
        "over_prompt_budget": False,
        "over_completion_budget": False,
        "over_batch_budget": False,
        "over_day_budget": False,
        "explore_floor_breached": False,
    }

    for event in run_events:
        event_type = str(event.get("event_type") or "")
        if not event_type.startswith("budget."):
            continue

        detail = event.get("payload")
        payload = detail if isinstance(detail, dict) else {}
        ts = str(event.get("created_at") or "")
        prompt_value = _to_int(payload.get("prompt_tokens"))
        completion_value = _to_int(payload.get("completion_tokens"))

        prompt_series.append({"ts": ts, "value": prompt_value, "limit": budget.max_prompt_tokens})
        completion_series.append({"ts": ts, "value": completion_value, "limit": budget.max_completion_tokens})

        exceeded = payload.get("budget_exceeded")
        exceeded_map = exceeded if isinstance(exceeded, dict) else {}
        flags["over_prompt_budget"] = flags["over_prompt_budget"] or bool(exceeded_map.get("request_prompt"))
        flags["over_completion_budget"] = flags["over_completion_budget"] or bool(
            exceeded_map.get("request_completion")
        )
        flags["over_batch_budget"] = flags["over_batch_budget"] or bool(exceeded_map.get("batch_total"))
        flags["over_day_budget"] = flags["over_day_budget"] or bool(exceeded_map.get("day_total"))
        flags["explore_floor_breached"] = flags["explore_floor_breached"] or bool(
            exceeded_map.get("explore_floor")
        )

        if event_type == "budget.fallback_applied":
            fallback_timeline.append(
                {
                    "ts": ts,
                    "phase": str(payload.get("fallback_phase") or "unknown"),
                    "factor": _to_float(payload.get("fallback_factor")),
                    "fallback_count": _to_int(payload.get("fallback_count")),
                    "selected_topk": payload.get("selected_topk") if isinstance(payload.get("selected_topk"), dict) else {},
                }
            )

        if event_type == "budget.blocked":
            flags["budget_blocked"] = True

        latest_payload = payload

    gauges = {
        "prompt_tokens": {
            "value": _to_int(latest_payload.get("prompt_tokens")),
            "limit": budget.max_prompt_tokens,
        },
        "completion_tokens": {
            "value": _to_int(latest_payload.get("completion_tokens")),
            "limit": budget.max_completion_tokens,
        },
        "batch_tokens": {
            "value": _to_int(latest_payload.get("projected_batch_tokens")) or usage.total_run_tokens,
            "limit": budget.max_tokens_per_batch,
        },
        "day_tokens": {
            "value": _to_int(latest_payload.get("projected_day_tokens")) or usage.total_day_tokens,
            "limit": budget.max_tokens_per_day,
        },
    }

    return {
        "run_id": run_id,
        "series": {
            "prompt_tokens": prompt_series,
            "completion_tokens": completion_series,
            "fallback_timeline": fallback_timeline,
        },
        "gauges": gauges,
        "flags": flags,
    }


def build_kpi_payload(
    *,
    run_id: str,
    run_events: list[dict[str, Any]],
    budget: LLMBudgetConfig,
) -> dict[str, Any]:
    """Build coverage/novelty/explore KPI payload for dashboard endpoint."""
    coverage_series: list[dict[str, Any]] = []
    novelty_series: list[dict[str, Any]] = []
    explore_series: list[dict[str, Any]] = []

    latest_coverage = 0.0
    latest_novelty = 0.0
    latest_explore_ratio = 0.0

    for event in run_events:
        event_type = str(event.get("event_type") or "")
        if not event_type.startswith("budget."):
            continue

        detail = event.get("payload")
        payload = detail if isinstance(detail, dict) else {}
        ts = str(event.get("created_at") or "")

        coverage = _to_float(payload.get("coverage_kpi"))
        novelty = _to_float(payload.get("novelty_kpi"))

        lane_ratio = payload.get("lane_ratio")
        lane_map = lane_ratio if isinstance(lane_ratio, dict) else {}
        explore_ratio = _to_float(lane_map.get("explore_ratio"))

        coverage_series.append({"ts": ts, "value": coverage})
        novelty_series.append({"ts": ts, "value": novelty})
        explore_series.append({"ts": ts, "value": explore_ratio})

        latest_coverage = coverage
        latest_novelty = novelty
        latest_explore_ratio = explore_ratio

    flags = {
        "low_novelty": latest_novelty < 0.15,
        "low_coverage": latest_coverage < 1.0,
        "explore_floor_breached": latest_explore_ratio < max(0.0, budget.explore_ratio - 0.15),
    }

    return {
        "run_id": run_id,
        "series": {
            "coverage": coverage_series,
            "novelty": novelty_series,
            "explore_ratio": explore_series,
        },
        "gauges": {
            "coverage": {"value": latest_coverage, "limit": None},
            "novelty": {"value": latest_novelty, "limit": 1.0},
            "explore_ratio": {"value": latest_explore_ratio, "limit": budget.explore_ratio},
        },
        "flags": flags,
    }


def _evaluate_budget(
    *,
    prompt: str,
    pack: RetrievalPack,
    budget: LLMBudgetConfig,
    usage: UsageSnapshot,
    seen_combo_keys: set[str],
    max_output_tokens: int,
    fallback_count: int,
    explore_floor_targets: tuple[int, int],
) -> BudgetEvaluation:
    prompt_tokens = rough_token_estimate(prompt)
    completion_budget = max(1, min(int(max_output_tokens), int(budget.max_completion_tokens)))

    projected_batch = usage.total_run_tokens + prompt_tokens + completion_budget
    projected_day = usage.total_day_tokens + prompt_tokens + completion_budget

    selected_topk = {
        "subcategories": len(pack.selected_subcategories),
        "datasets": len(pack.candidate_datasets),
        "fields": len(pack.candidate_fields),
        "operators": len(pack.candidate_operators),
    }
    lane_ratio = _lane_ratio(pack)
    coverage_kpi = float(len(set(pack.selected_subcategories)))
    novelty_kpi, combo_sample = _novelty_kpi(pack, seen_combo_keys)
    explore_floor = _explore_floor_preserved(pack, explore_floor_targets)

    exceeded = {
        "request_prompt": prompt_tokens > int(budget.max_prompt_tokens),
        "request_completion": completion_budget > int(budget.max_completion_tokens),
        "batch_total": projected_batch > int(budget.max_tokens_per_batch),
        "day_total": projected_day > int(budget.max_tokens_per_day),
        "explore_floor": not explore_floor,
    }

    passed = not any(exceeded.values())
    estimated_request_cost = estimate_cost_usd(prompt_tokens, completion_budget, budget)

    return BudgetEvaluation(
        passed=passed,
        prompt_tokens_rough=prompt_tokens,
        completion_tokens_budget=completion_budget,
        projected_batch_tokens=projected_batch,
        projected_day_tokens=projected_day,
        selected_topk=selected_topk,
        lane_ratio=lane_ratio,
        coverage_kpi=coverage_kpi,
        novelty_kpi=novelty_kpi,
        combo_sample=combo_sample,
        explore_floor_preserved=explore_floor,
        exceeded=exceeded,
        fallback_count=fallback_count,
        estimated_request_cost_usd=estimated_request_cost,
    )


def _shrink_pack(pack: RetrievalPack, *, phase: str, factor: float, budget: LLMBudgetConfig) -> None:
    if phase == "fields":
        _shrink_fields(pack, factor=factor, budget=budget)
        return
    if phase == "operators":
        _shrink_operators(pack, factor=factor, budget=budget)
        return
    if phase == "subcategories":
        _shrink_subcategories(pack, factor=factor, budget=budget)
        return


def _shrink_fields(pack: RetrievalPack, *, factor: float, budget: LLMBudgetConfig) -> None:
    current = list(pack.candidate_fields)
    if len(current) <= 1:
        return

    target_total = _target_total(len(current), factor, min_total=1)
    pack.candidate_fields = _trim_field_candidates(current, target_total=target_total, budget=budget)


def _shrink_operators(pack: RetrievalPack, *, factor: float, budget: LLMBudgetConfig) -> None:
    current = list(pack.candidate_operators)
    if len(current) <= 1:
        return

    target_total = _target_total(len(current), factor, min_total=1)
    pack.candidate_operators = _trim_operator_candidates(current, target_total=target_total, budget=budget)


def _shrink_subcategories(pack: RetrievalPack, *, factor: float, budget: LLMBudgetConfig) -> None:
    if len(pack.selected_subcategories) <= 1:
        return

    target_total = _target_total(len(pack.selected_subcategories), factor, min_total=1)

    exploit_subcats = _ordered_unique(
        [row.subcategory_id for row in pack.candidate_datasets if row.lane == "exploit" and row.subcategory_id]
    )
    explore_subcats = _ordered_unique(
        [row.subcategory_id for row in pack.candidate_datasets if row.lane == "explore" and row.subcategory_id]
    )

    exploit_target, explore_target = _allocate_lane_counts(
        target_total=target_total,
        exploit_available=len(exploit_subcats),
        explore_available=len(explore_subcats),
        explore_ratio=budget.normalized_lane_ratio()[1],
        min_explore=1 if budget.min_explore_candidates_per_batch > 0 else 0,
    )

    keep: list[str] = []
    keep.extend(exploit_subcats[:exploit_target])
    keep.extend(explore_subcats[:explore_target])

    if len(keep) < target_total:
        for subcat in pack.selected_subcategories:
            if subcat in keep:
                continue
            keep.append(subcat)
            if len(keep) >= target_total:
                break

    keep_set = set(keep)
    pack.selected_subcategories = [item for item in pack.selected_subcategories if item in keep_set]

    pack.candidate_datasets = [row for row in pack.candidate_datasets if row.subcategory_id in keep_set]
    keep_dataset_ids = {row.id for row in pack.candidate_datasets}
    if keep_dataset_ids:
        pack.candidate_fields = [row for row in pack.candidate_fields if row.dataset_id in keep_dataset_ids]


def _trim_field_candidates(
    rows: list[FieldCandidate],
    *,
    target_total: int,
    budget: LLMBudgetConfig,
) -> list[FieldCandidate]:
    if target_total >= len(rows):
        return rows

    exploit = [row for row in rows if row.lane == "exploit"]
    explore = [row for row in rows if row.lane == "explore"]

    exploit_target, explore_target = _allocate_lane_counts(
        target_total=target_total,
        exploit_available=len(exploit),
        explore_available=len(explore),
        explore_ratio=budget.normalized_lane_ratio()[1],
        min_explore=min(budget.min_explore_candidates_per_batch, target_total),
    )

    keep_exploit = {row.id for row in exploit[:exploit_target]}
    keep_explore = {row.id for row in explore[:explore_target]}

    out: list[FieldCandidate] = []
    for row in rows:
        if row.lane == "exploit" and row.id in keep_exploit:
            out.append(row)
            keep_exploit.discard(row.id)
        elif row.lane == "explore" and row.id in keep_explore:
            out.append(row)
            keep_explore.discard(row.id)
        if len(out) >= target_total:
            break
    return out


def _trim_operator_candidates(
    rows: list[OperatorCandidate],
    *,
    target_total: int,
    budget: LLMBudgetConfig,
) -> list[OperatorCandidate]:
    if target_total >= len(rows):
        return rows

    exploit = [row for row in rows if row.lane == "exploit"]
    explore = [row for row in rows if row.lane == "explore"]

    exploit_target, explore_target = _allocate_lane_counts(
        target_total=target_total,
        exploit_available=len(exploit),
        explore_available=len(explore),
        explore_ratio=budget.normalized_lane_ratio()[1],
        min_explore=min(budget.min_explore_candidates_per_batch, target_total),
    )

    keep_exploit = {row.name for row in exploit[:exploit_target]}
    keep_explore = {row.name for row in explore[:explore_target]}

    out: list[OperatorCandidate] = []
    for row in rows:
        if row.lane == "exploit" and row.name in keep_exploit:
            out.append(row)
            keep_exploit.discard(row.name)
        elif row.lane == "explore" and row.name in keep_explore:
            out.append(row)
            keep_explore.discard(row.name)
        if len(out) >= target_total:
            break
    return out


def _sync_pack_contracts(pack: RetrievalPack, budget: LLMBudgetConfig) -> None:
    exploit_fields = [row.id for row in pack.candidate_fields if row.lane == "exploit"]
    explore_fields = [row.id for row in pack.candidate_fields if row.lane == "explore"]
    exploit_ops = [row.name for row in pack.candidate_operators if row.lane == "exploit"]
    explore_ops = [row.name for row in pack.candidate_operators if row.lane == "explore"]

    pack.lanes = {
        "exploit": LaneSelection(field_ids=exploit_fields, operator_names=exploit_ops),
        "explore": LaneSelection(field_ids=explore_fields, operator_names=explore_ops),
    }

    dataset_subcats = _ordered_unique([row.subcategory_id for row in pack.candidate_datasets if row.subcategory_id])
    if dataset_subcats:
        preferred = [value for value in pack.selected_subcategories if value in set(dataset_subcats)]
        extras = [value for value in dataset_subcats if value not in set(preferred)]
        pack.selected_subcategories = preferred + extras

    counts = {
        "subcategories": len(pack.selected_subcategories),
        "datasets": len(pack.candidate_datasets),
        "fields": len(pack.candidate_fields),
        "operators": len(pack.candidate_operators),
    }
    pack.telemetry = RetrievalTelemetry(
        retrieval_ms=max(0, int(pack.telemetry.retrieval_ms if pack.telemetry else 0)),
        candidate_counts=counts,
    )

    payload = {
        "query": pack.query,
        "selected_subcategories": pack.selected_subcategories,
        "candidate_datasets": [row.model_dump(mode="python") for row in pack.candidate_datasets],
        "candidate_fields": [row.model_dump(mode="python") for row in pack.candidate_fields],
        "candidate_operators": [row.model_dump(mode="python") for row in pack.candidate_operators],
        "lanes": {key: lane.model_dump(mode="python") for key, lane in pack.lanes.items()},
    }
    chars = len(json.dumps(payload, ensure_ascii=False))
    pack.token_estimate = RetrievalTokenEstimate(
        input_chars=chars,
        input_tokens_rough=rough_token_estimate(chars),
    )

    max_items = dict(pack.context_guard.max_items or {})
    max_items.update(counts)
    pack.context_guard.max_items = max_items

    policy = dict(pack.budget_policy or {})
    policy["llm_budget"] = {
        "max_prompt_tokens": budget.max_prompt_tokens,
        "max_completion_tokens": budget.max_completion_tokens,
        "max_tokens_per_batch": budget.max_tokens_per_batch,
        "max_tokens_per_day": budget.max_tokens_per_day,
    }
    pack.budget_policy = policy


def _pack_signature(pack: RetrievalPack) -> tuple[Any, ...]:
    return (
        tuple(row.id for row in pack.candidate_fields),
        tuple(row.name for row in pack.candidate_operators),
        tuple(pack.selected_subcategories),
    )


def _target_total(current_total: int, factor: float, *, min_total: int) -> int:
    if current_total <= min_total:
        return current_total
    target = max(min_total, int(math.floor(current_total * float(factor))))
    if target >= current_total:
        return max(min_total, current_total - 1)
    return target


def _allocate_lane_counts(
    *,
    target_total: int,
    exploit_available: int,
    explore_available: int,
    explore_ratio: float,
    min_explore: int,
) -> tuple[int, int]:
    if target_total <= 0:
        return 0, 0

    exploit_available = max(0, int(exploit_available))
    explore_available = max(0, int(explore_available))
    min_explore = max(0, int(min_explore))

    if exploit_available + explore_available <= target_total:
        return exploit_available, explore_available

    explore_target = int(round(target_total * max(0.0, explore_ratio)))
    if explore_available > 0 and min_explore > 0:
        explore_target = max(explore_target, min(min_explore, target_total))
    explore_target = min(explore_target, explore_available, target_total)

    exploit_target = min(exploit_available, max(0, target_total - explore_target))
    if exploit_available > 0 and exploit_target <= 0:
        exploit_target = 1
        explore_target = max(0, target_total - exploit_target)

    while exploit_target + explore_target < target_total:
        if exploit_target < exploit_available:
            exploit_target += 1
            continue
        if explore_target < explore_available:
            explore_target += 1
            continue
        break

    return exploit_target, explore_target


def _lane_ratio(pack: RetrievalPack) -> dict[str, Any]:
    exploit_fields = sum(1 for row in pack.candidate_fields if row.lane == "exploit")
    explore_fields = sum(1 for row in pack.candidate_fields if row.lane == "explore")
    exploit_ops = sum(1 for row in pack.candidate_operators if row.lane == "exploit")
    explore_ops = sum(1 for row in pack.candidate_operators if row.lane == "explore")

    exploit_total = exploit_fields + exploit_ops
    explore_total = explore_fields + explore_ops
    total = max(1, exploit_total + explore_total)

    return {
        "exploit_ratio": round(exploit_total / total, 4),
        "explore_ratio": round(explore_total / total, 4),
        "exploit_count": exploit_total,
        "explore_count": explore_total,
        "fields": {
            "exploit": exploit_fields,
            "explore": explore_fields,
        },
        "operators": {
            "exploit": exploit_ops,
            "explore": explore_ops,
        },
    }


def _novelty_kpi(pack: RetrievalPack, seen_combo_keys: set[str]) -> tuple[float, list[str]]:
    field_ids = [row.id for row in pack.candidate_fields[: min(20, len(pack.candidate_fields))]]
    operator_names = [row.name for row in pack.candidate_operators[: min(20, len(pack.candidate_operators))]]

    combos = [f"{field_id}::{op_name}" for field_id in field_ids for op_name in operator_names]
    if not combos:
        return 0.0, []

    unique_combos = _ordered_unique(combos)
    seen = set(seen_combo_keys)
    new_count = len([key for key in unique_combos if key not in seen])
    novelty = new_count / max(1, len(unique_combos))

    return round(float(novelty), 4), unique_combos[:64]


def _explore_floor_targets(pack: RetrievalPack, budget: LLMBudgetConfig) -> tuple[int, int]:
    floor = max(0, int(budget.min_explore_candidates_per_batch))
    if floor <= 0:
        return 0, 0

    explore_fields = sum(1 for row in pack.candidate_fields if row.lane == "explore")
    explore_ops = sum(1 for row in pack.candidate_operators if row.lane == "explore")
    return min(floor, explore_fields), min(floor, explore_ops)


def _explore_floor_preserved(pack: RetrievalPack, targets: tuple[int, int]) -> bool:
    field_target, op_target = targets
    explore_fields = sum(1 for row in pack.candidate_fields if row.lane == "explore")
    explore_ops = sum(1 for row in pack.candidate_operators if row.lane == "explore")
    return explore_fields >= max(0, field_target) and explore_ops >= max(0, op_target)


def _ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _first_nonneg_int(payload: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            out = int(value)
            if out >= 0:
                return out
        except Exception:
            continue
    return -1


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
