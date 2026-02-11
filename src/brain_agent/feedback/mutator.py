"""Feedback agent: classify failures and generate new candidates."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from ..runtime.event_bus import EventBus
from ..schemas import CandidateAlpha, FailureReason, ScoreCard


WINDOW_VALUES = [3, 5, 10, 20, 40, 60, 120]
DECAY_VALUES = [5, 10, 15, 20, 30]
TRUNCATION_VALUES = [0.05, 0.08, 0.10, 0.13]


class FeedbackMutator:
    """Generate parameter and expression mutations from evaluator feedback."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def classify_failure(self, card: ScoreCard) -> FailureReason:
        reasons = card.reasons

        if any("sharpe" in r for r in reasons):
            return FailureReason(
                label="LOW_SHARPE",
                rationale="Signal noise appears high compared to return consistency.",
                actions=["add_smoothing", "add_rank_or_zscore", "winsorize"],
            )

        if any("turnover" in r for r in reasons):
            return FailureReason(
                label="HIGH_OR_LOW_TURNOVER",
                rationale="Turnover outside target band; decay/truncation likely mis-set.",
                actions=["increase_decay", "strengthen_truncation", "add_ts_delay"],
            )

        if any("coverage" in r for r in reasons):
            return FailureReason(
                label="LOW_COVERAGE",
                rationale="Coverage likely insufficient due to sparse fields.",
                actions=["swap_dataset", "relax_nan_handling"],
            )

        return FailureReason(
            label="GENERAL_IMPROVEMENT",
            rationale="No single dominant failure reason; run broad local search.",
            actions=["parameter_grid", "operator_swap"],
        )

    def parameter_search(self, candidate: CandidateAlpha, *, max_variants: int = 10) -> list[CandidateAlpha]:
        """Generate bounded parameter grid variations for multi-simulation."""
        out: list[CandidateAlpha] = []

        for decay in DECAY_VALUES:
            for trunc in TRUNCATION_VALUES:
                variant = candidate.model_copy(deep=True)
                variant.simulation_settings.settings.decay = decay
                variant.simulation_settings.settings.truncation = trunc
                out.append(variant)
                if len(out) >= max_variants:
                    return out
        return out

    def mutate_expression(
        self,
        expression: str,
        *,
        max_variants: int = 8,
        window_values: Iterable[int] = WINDOW_VALUES,
    ) -> list[str]:
        """Generate expression-level mutations with operator swaps and window changes."""
        variants: list[str] = []

        swaps = [
            ("ts_mean", "ts_median"),
            ("ts_median", "ts_mean"),
            ("rank", "zscore"),
            ("zscore", "rank"),
        ]

        for a, b in swaps:
            if a in expression:
                variants.append(expression.replace(a, b, 1))

        if expression.startswith("rank("):
            variants.append(f"zscore({expression})")
        else:
            variants.append(f"rank({expression})")

        # Replace first integer literal (typically window parameter) with configured values.
        int_match = re.search(r"\b\d+\b", expression)
        if int_match:
            old = int_match.group(0)
            for val in window_values:
                if str(val) == old:
                    continue
                variants.append(expression[: int_match.start()] + str(val) + expression[int_match.end() :])

        deduped: list[str] = []
        seen: set[str] = set()
        for variant in variants:
            norm = " ".join(variant.split())
            if norm in seen:
                continue
            seen.add(norm)
            deduped.append(variant)
            if len(deduped) >= max_variants:
                break
        return deduped

    def propose_mutations(
        self,
        candidate: CandidateAlpha,
        card: ScoreCard,
        *,
        max_variants: int = 10,
        validator: object | None = None,
        run_id: str | None = None,
        parent_alpha_id: str | None = None,
    ) -> list[CandidateAlpha]:
        """Create new candidate variants and optionally keep only statically valid ones."""
        failure = self.classify_failure(card)

        base = candidate.model_copy(deep=True)
        expression = base.simulation_settings.regular or ""

        tagged_variants: list[tuple[CandidateAlpha, str]] = []
        for variant in self.parameter_search(base, max_variants=max_variants):
            tagged_variants.append((variant, "parameter_search"))
            if len(tagged_variants) >= max_variants:
                break

        if len(tagged_variants) < max_variants:
            expr_mutations = self.mutate_expression(expression, max_variants=max_variants)
            for expr in expr_mutations:
                copy = candidate.model_copy(deep=True)
                copy.simulation_settings.regular = expr
                tagged_variants.append((copy, "expression_mutation"))
                if len(tagged_variants) >= max_variants:
                    break

        selected: list[tuple[CandidateAlpha, str]]
        if validator is None:
            selected = tagged_variants[:max_variants]
        else:
            selected = []
            for variant, source in tagged_variants:
                report = validator.validate(variant.simulation_settings.regular or "")
                if report.is_valid:
                    selected.append((variant, source))
                if len(selected) >= max_variants:
                    break
            # If every mutation failed validation, keep generated variants for inspection.
            if not selected:
                selected = tagged_variants[:max_variants]

        out = [item for item, _ in selected]
        self._emit_lineage_events(
            parent=candidate,
            variants=selected,
            card=card,
            failure=failure,
            run_id=run_id,
            parent_alpha_id=parent_alpha_id,
        )
        return out

    def _emit_lineage_events(
        self,
        *,
        parent: CandidateAlpha,
        variants: list[tuple[CandidateAlpha, str]],
        card: ScoreCard,
        failure: FailureReason,
        run_id: str | None,
        parent_alpha_id: str | None,
    ) -> None:
        if self.event_bus is None or not run_id:
            return

        parent_key = _candidate_key(parent)
        for idx, (child, source) in enumerate(variants):
            child_key = _candidate_key(child)
            self.event_bus.publish(
                event_type="mutation.child_created",
                run_id=run_id,
                idea_id=parent.idea_id,
                stage="feedback",
                message="Mutation child candidate created",
                severity="info",
                payload={
                    "parent_alpha_id": parent_alpha_id,
                    "parent_candidate_key": parent_key,
                    "child_candidate_key": child_key,
                    "mutation_index": idx,
                    "mutation_source": source,
                    "failure_label": failure.label,
                    "failure_actions": failure.actions,
                    "scorecard_reasons": list(card.reasons),
                    "candidate_lane": child.generation_notes.candidate_lane or parent.generation_notes.candidate_lane,
                },
            )


def _candidate_key(candidate: CandidateAlpha) -> str:
    settings = candidate.simulation_settings.model_dump(mode="python", exclude_none=True)
    expression = candidate.simulation_settings.regular or candidate.simulation_settings.combo or ""
    basis = json.dumps(settings, ensure_ascii=False, sort_keys=True) + "|" + expression.strip()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
