"""Step-21 validation-first repair/simulation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..evaluation.evaluator import Evaluator
from ..feedback.mutator import FeedbackMutator
from ..generation.validation_gate import ValidationGate, dump_instruction_json
from ..retrieval.pack_builder import (
    RetrievalBudgetConfig,
    RetrievalExpansionPolicy,
    RetrievalLaneBudget,
    RetrievalPack,
    build_retrieval_pack,
)
from ..runtime.event_bus import EventBus
from ..schemas import AlphaResult, CandidateAlpha, IdeaSpec, ScoreCard
from ..simulation.runner import SimulationRunner
from ..storage.sqlite_store import MetadataStore


@dataclass
class ValidationLoopResult:
    run_id: str
    candidate: CandidateAlpha
    validation_passed: bool
    validation_attempts: int
    error_codes: list[str] = field(default_factory=list)
    retrieval_expanded: bool = False
    simulation_results: list[AlphaResult] = field(default_factory=list)
    scorecards: list[ScoreCard] = field(default_factory=list)
    mutation_count: int = 0
    event_order_violation: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "validation_passed": self.validation_passed,
            "validation_attempts": self.validation_attempts,
            "error_codes": self.error_codes,
            "retrieval_expanded": self.retrieval_expanded,
            "simulated": len(self.simulation_results),
            "evaluated": len(self.scorecards),
            "mutation_count": self.mutation_count,
            "event_order_violation": self.event_order_violation,
            "alpha_ids": [item.alpha_id for item in self.simulation_results],
        }


class ValidationLoopOrchestrator:
    """Execute strict validation -> repair -> simulation -> evaluation flow."""

    def __init__(
        self,
        *,
        store: MetadataStore,
        gate: ValidationGate,
        simulation_runner: SimulationRunner,
        evaluator: Evaluator,
        mutator: FeedbackMutator,
        event_bus: EventBus | None = None,
        max_repair_attempts: int = 3,
        stop_on_repeated_error: bool = True,
        meta_dir: str | Path = "data/meta",
    ) -> None:
        self.store = store
        self.gate = gate
        self.simulation_runner = simulation_runner
        self.evaluator = evaluator
        self.mutator = mutator
        self.event_bus = event_bus or EventBus(store=store)
        self.max_repair_attempts = max(0, int(max_repair_attempts))
        self.stop_on_repeated_error = bool(stop_on_repeated_error)
        self.meta_dir = Path(meta_dir)

    def run(
        self,
        *,
        idea: IdeaSpec,
        candidate: CandidateAlpha,
        retrieval_pack: RetrievalPack,
        run_id: str | None = None,
        simulate: bool = True,
    ) -> ValidationLoopResult:
        active_run_id = str(run_id or f"run-vloop-{uuid4().hex[:12]}")
        working_candidate = candidate.model_copy(deep=True)
        working_pack = retrieval_pack.model_copy(deep=True)

        attempts = 0
        error_codes: list[str] = []
        signatures: list[str] = []
        retrieval_expanded = False

        self.event_bus.publish(
            event_type="validation.started",
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="validation",
            message="Validation stage started",
            severity="info",
            payload={
                "max_repair_attempts": self.max_repair_attempts,
                "stop_on_repeated_error": self.stop_on_repeated_error,
                "candidate_lane": working_candidate.generation_notes.candidate_lane,
            },
        )

        validation_passed = False
        while True:
            gate_result = self.gate.validate_candidate(working_candidate)
            signature = gate_result.error_signature
            repeat_count = _repeat_streak(signatures, signature) + (0 if signature == "VALID" else 1)
            error_codes = [issue.code for issue in gate_result.issues]

            if gate_result.is_valid:
                event_type = "validation.passed" if attempts == 0 else "validation.retry_passed"
                self.event_bus.publish(
                    event_type=event_type,
                    run_id=active_run_id,
                    idea_id=idea.idea_id,
                    stage="validation",
                    message="Static validation passed",
                    severity="info",
                    payload={
                        "attempt": attempts,
                        "error_codes": [],
                    },
                )
                validation_passed = True
                break

            terminal_event = "validation.failed" if attempts == 0 else "validation.retry_failed"
            self.event_bus.publish(
                event_type=terminal_event,
                run_id=active_run_id,
                idea_id=idea.idea_id,
                stage="validation",
                message="Static validation failed",
                severity="warn",
                payload={
                    "attempt": attempts,
                    "error_codes": error_codes,
                    "errors": [issue.message for issue in gate_result.issues],
                    "repeat_count": repeat_count,
                },
            )
            signatures.append(signature)

            if attempts >= self.max_repair_attempts:
                break

            attempts += 1
            expanded_now = False
            threshold = _expansion_threshold(working_pack)
            if (not retrieval_expanded) and _expansion_enabled(working_pack) and repeat_count >= threshold:
                old_counts = _pack_counts(working_pack)
                working_pack = self._expand_retrieval_pack(idea=idea, pack=working_pack)
                new_counts = _pack_counts(working_pack)
                retrieval_expanded = True
                expanded_now = True
                self.event_bus.publish(
                    event_type="validation.retrieval_expanded",
                    run_id=active_run_id,
                    idea_id=idea.idea_id,
                    stage="validation",
                    message="Repeated errors triggered retrieval expansion branch",
                    severity="warn",
                    payload={
                        "attempt": attempts,
                        "repeat_count": repeat_count,
                        "threshold": threshold,
                        "topk_before": old_counts,
                        "topk_after": new_counts,
                    },
                )
            elif self.stop_on_repeated_error and repeat_count >= threshold and not expanded_now:
                self.event_bus.publish(
                    event_type="validation.retry_aborted_repeated_error",
                    run_id=active_run_id,
                    idea_id=idea.idea_id,
                    stage="validation",
                    message="Retry aborted due to repeated identical validation errors",
                    severity="warn",
                    payload={
                        "attempt": attempts,
                        "repeat_count": repeat_count,
                        "threshold": threshold,
                        "error_codes": error_codes,
                    },
                )
                break

            instruction = self.gate.build_repair_instruction(
                candidate=working_candidate,
                issues=gate_result.issues,
                retrieval_pack=working_pack,
                attempt=attempts,
                repeated_error_count=repeat_count,
                expanded_retrieval=expanded_now,
            )
            self.event_bus.publish(
                event_type="validation.retry_started",
                run_id=active_run_id,
                idea_id=idea.idea_id,
                stage="validation",
                message="Repair retry started",
                severity="info",
                payload={
                    "attempt": attempts,
                    "instruction": instruction,
                    "instruction_json": dump_instruction_json(instruction),
                },
            )
            working_candidate = self.gate.repair_candidate(
                candidate=working_candidate,
                issues=gate_result.issues,
                retrieval_pack=working_pack,
            )

        working_candidate.generation_notes.validation_passed = validation_passed
        working_candidate.generation_notes.validation_attempts = attempts + 1

        simulation_results: list[AlphaResult] = []
        scorecards: list[ScoreCard] = []
        mutations: list[CandidateAlpha] = []

        if validation_passed and simulate:
            queue_payload = {
                "validation_passed": True,
                "validation_attempts": working_candidate.generation_notes.validation_attempts,
                "candidate_lane": working_candidate.generation_notes.candidate_lane,
            }
            one = self.simulation_runner.run_candidate(
                working_candidate,
                run_id=active_run_id,
                queue_payload=queue_payload,
            )
            if one is not None:
                simulation_results.append(one)

            scorecards = self.evaluator.evaluate(
                simulation_results,
                run_id=active_run_id,
                idea_id=idea.idea_id,
            )

            for card in scorecards:
                if card.passed:
                    continue
                mutations.extend(
                    self.mutator.propose_mutations(
                        working_candidate,
                        card,
                        max_variants=3,
                        validator=self.gate.validator,
                        run_id=active_run_id,
                        parent_alpha_id=card.alpha_id,
                    )
                )
        elif validation_passed and not simulate:
            self.event_bus.publish(
                event_type="simulation.skipped_by_option",
                run_id=active_run_id,
                idea_id=idea.idea_id,
                stage="simulation",
                message="Simulation skipped by CLI option",
                severity="warn",
                payload={
                    "validation_passed": True,
                    "validation_attempts": working_candidate.generation_notes.validation_attempts,
                },
            )
            scorecards = self.evaluator.evaluate(
                [],
                run_id=active_run_id,
                idea_id=idea.idea_id,
            )
        else:
            self.event_bus.publish(
                event_type="simulation.blocked_validation",
                run_id=active_run_id,
                idea_id=idea.idea_id,
                stage="simulation",
                message="Simulation enqueue blocked because validation did not pass",
                severity="warn",
                payload={
                    "validation_passed": False,
                    "validation_attempts": working_candidate.generation_notes.validation_attempts,
                    "error_codes": error_codes,
                },
            )
            # Emit explicit empty completion marker for UI contracts.
            self.evaluator.evaluate(
                [],
                run_id=active_run_id,
                idea_id=idea.idea_id,
            )

        event_order_violation = self._detect_event_order_violation(
            run_id=active_run_id,
            expect_simulation=simulate and validation_passed,
        )
        if event_order_violation:
            self.event_bus.publish(
                event_type="validation.event_order_violation",
                run_id=active_run_id,
                idea_id=idea.idea_id,
                stage="validation",
                message="Event ordering contract violated",
                severity="warn",
                payload={"event_order_violation": True},
            )

        result = ValidationLoopResult(
            run_id=active_run_id,
            candidate=working_candidate,
            validation_passed=validation_passed,
            validation_attempts=working_candidate.generation_notes.validation_attempts,
            error_codes=error_codes,
            retrieval_expanded=retrieval_expanded,
            simulation_results=simulation_results,
            scorecards=scorecards,
            mutation_count=len(mutations),
            event_order_violation=event_order_violation,
        )
        self.event_bus.publish(
            event_type="run.summary",
            run_id=active_run_id,
            idea_id=idea.idea_id,
            stage="summary",
            message="Validation-first loop completed",
            severity="warn" if event_order_violation else "info",
            payload=result.to_payload(),
        )
        return result

    def _expand_retrieval_pack(self, *, idea: IdeaSpec, pack: RetrievalPack) -> RetrievalPack:
        factor = _expansion_factor(pack)
        exploit = pack.budget_policy.get("exploit")
        explore = pack.budget_policy.get("explore")
        exploit_budget = _lane_budget_from_payload(exploit, factor)
        explore_budget = _lane_budget_from_payload(explore, factor)

        expanded_budget = RetrievalBudgetConfig(
            exploit_ratio=float(pack.budget_policy.get("exploit_ratio") or 0.7),
            explore_ratio=float(pack.budget_policy.get("explore_ratio") or 0.3),
            exploit=exploit_budget,
            explore=explore_budget,
            expansion_policy=RetrievalExpansionPolicy(
                enabled=_expansion_enabled(pack),
                trigger_on_repeated_validation_error=_expansion_threshold(pack),
                topk_expand_factor=factor,
            ),
        )
        return build_retrieval_pack(
            idea=idea,
            store=self.store,
            budget=expanded_budget,
            meta_dir=self.meta_dir,
            query_override=pack.query,
        )

    def _detect_event_order_violation(self, *, run_id: str, expect_simulation: bool) -> bool:
        records = self.store.list_event_records_for_run(run_id=run_id, limit=5000)
        events = [_event_type_from_record(row) for row in records]
        if not events:
            return True

        alpha_idx = _first_index(events, {"agent.alpha_generated"})
        validation_start_idx = _first_index(events, {"validation.started"})
        if alpha_idx == -1 or validation_start_idx == -1 or alpha_idx >= validation_start_idx:
            return True

        terminal_idx = _first_index(events, {"validation.failed", "validation.passed"}, start=validation_start_idx + 1)
        if terminal_idx == -1:
            return True

        if _retry_order_violation(events):
            return True

        validation_passed = ("validation.passed" in events) or ("validation.retry_passed" in events)
        simulation_completed_idx = _first_index(events, {"simulation.completed", "simulation_completed"})
        simulation_enqueued_idx = _first_index(events, {"simulation.enqueued"})
        simulation_started_idx = _first_index(events, {"simulation.started"})
        simulation_skipped_idx = _first_index(events, {"simulation_skipped_duplicate"})

        if validation_passed and expect_simulation:
            duplicate_only_path = (
                simulation_skipped_idx != -1
                and simulation_enqueued_idx == -1
                and simulation_started_idx == -1
                and simulation_completed_idx == -1
            )
            if not duplicate_only_path:
                if simulation_enqueued_idx == -1 or simulation_started_idx == -1:
                    return True
                if simulation_enqueued_idx >= simulation_started_idx:
                    return True
                if simulation_completed_idx != -1 and simulation_started_idx >= simulation_completed_idx:
                    return True
        else:
            if simulation_enqueued_idx != -1 or simulation_started_idx != -1 or simulation_completed_idx != -1:
                return True

        evaluation_idx = _first_index(events, {"evaluation.completed"})
        if evaluation_idx == -1:
            return True
        if simulation_completed_idx != -1 and evaluation_idx <= simulation_completed_idx:
            return True
        if simulation_skipped_idx != -1 and simulation_completed_idx == -1 and evaluation_idx <= simulation_skipped_idx:
            return True
        if simulation_completed_idx == -1 and evaluation_idx <= terminal_idx:
            return True

        return False


def _lane_budget_from_payload(payload: Any, factor: float) -> RetrievalLaneBudget:
    row = payload if isinstance(payload, dict) else {}
    return RetrievalLaneBudget(
        subcategories=_scaled_count(row.get("subcategories"), factor),
        datasets=_scaled_count(row.get("datasets"), factor),
        fields=_scaled_count(row.get("fields"), factor),
        operators=_scaled_count(row.get("operators"), factor),
    )


def _scaled_count(value: Any, factor: float) -> int:
    base = max(1, int(value) if isinstance(value, int) else int(float(value or 1)))
    scaled = int(round(base * max(1.0, float(factor))))
    if scaled <= base:
        scaled = base + 1
    return scaled


def _repeat_streak(history: list[str], signature: str) -> int:
    if not signature:
        return 0
    count = 0
    for item in reversed(history):
        if item != signature:
            break
        count += 1
    return count


def _pack_counts(pack: RetrievalPack) -> dict[str, int]:
    return {
        "subcategories": len(pack.selected_subcategories),
        "datasets": len(pack.candidate_datasets),
        "fields": len(pack.candidate_fields),
        "operators": len(pack.candidate_operators),
    }


def _expansion_enabled(pack: RetrievalPack) -> bool:
    policy = pack.expansion_policy if isinstance(pack.expansion_policy, dict) else {}
    return bool(policy.get("enabled", True))


def _expansion_threshold(pack: RetrievalPack) -> int:
    policy = pack.expansion_policy if isinstance(pack.expansion_policy, dict) else {}
    raw = policy.get("trigger_on_repeated_validation_error", 2)
    try:
        return max(1, int(raw))
    except Exception:
        return 2


def _expansion_factor(pack: RetrievalPack) -> float:
    policy = pack.expansion_policy if isinstance(pack.expansion_policy, dict) else {}
    raw = policy.get("topk_expand_factor", 1.5)
    try:
        value = float(raw)
    except Exception:
        return 1.5
    return max(1.0, value)


def _event_type_from_record(record: dict[str, Any]) -> str:
    payload = record.get("payload")
    row = payload if isinstance(payload, dict) else {}
    return str(row.get("event_type") or record.get("event_type") or "")


def _first_index(values: list[str], keys: set[str], start: int = 0) -> int:
    for idx in range(max(0, int(start)), len(values)):
        if values[idx] in keys:
            return idx
    return -1


def _retry_order_violation(events: list[str]) -> bool:
    retry_starts = [idx for idx, name in enumerate(events) if name == "validation.retry_started"]
    for idx in retry_starts:
        next_retry = _first_index(events, {"validation.retry_started"}, start=idx + 1)
        end = len(events) if next_retry == -1 else next_retry
        window = events[idx + 1 : end]
        if not any(name in {"validation.retry_failed", "validation.retry_passed"} for name in window):
            return True
    return False
