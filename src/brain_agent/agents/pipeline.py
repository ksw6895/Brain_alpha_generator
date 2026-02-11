"""Multi-agent pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..evaluation.evaluator import Evaluator
from ..feedback.mutator import FeedbackMutator
from ..metadata.sync import sync_all_metadata
from ..schemas import CandidateAlpha, IdeaSpec, ScoreCard, SimulationTarget
from ..simulation.runner import SimulationRunner
from ..storage.sqlite_store import MetadataStore


@dataclass
class PipelineCycleResult:
    simulated_count: int
    passed_count: int
    total_mutations: int
    top_alpha_ids: list[str]


class BrainPipeline:
    """Reference pipeline implementation for Step 7 architecture."""

    def __init__(
        self,
        *,
        session: Any,
        store: MetadataStore,
        simulation_runner: SimulationRunner,
        evaluator: Evaluator,
        mutator: FeedbackMutator,
    ) -> None:
        self.session = session
        self.store = store
        self.simulation_runner = simulation_runner
        self.evaluator = evaluator
        self.mutator = mutator

    def run_metadata_sync(self, target: SimulationTarget) -> dict[str, int]:
        """MetaSync Agent responsibility."""
        summary = sync_all_metadata(self.session, self.store, target)
        self.store.append_event(
            "metadata_sync",
            {
                **summary,
                "run_id": "pipeline-metadata-sync",
                "idea_id": "system",
                "stage": "metadata_sync",
                "message": "Metadata sync completed",
                "severity": "info",
            },
        )
        return summary

    def run_cycle(self, candidates: list[CandidateAlpha]) -> PipelineCycleResult:
        """Run one evaluate-feedback loop for candidate alphas."""
        results = self.simulation_runner.run_candidates_multi(candidates)
        scorecards = self.evaluator.evaluate(results)
        passed = [card for card in scorecards if card.passed]

        mutations = self._mutate_from_failures(candidates, scorecards)

        self.store.append_event(
            "cycle_completed",
            {
                "simulated": len(results),
                "passed": len(passed),
                "mutations": len(mutations),
                "run_id": "pipeline-cycle",
                "idea_id": "system",
                "stage": "pipeline_cycle",
                "message": "Evaluation/feedback cycle completed",
                "severity": "info",
            },
        )

        return PipelineCycleResult(
            simulated_count=len(results),
            passed_count=len(passed),
            total_mutations=len(mutations),
            top_alpha_ids=[card.alpha_id for card in passed[:5]],
        )

    def build_candidates_from_ideas(self, ideas: list[IdeaSpec]) -> list[CandidateAlpha]:
        """FastExpr Builder placeholder using safe starter template.

        Real production flow should replace this with LLM-based expression generation.
        """
        out: list[CandidateAlpha] = []
        for idea in ideas:
            expr = "rank(ts_delta(log(close), 5))"
            candidate = CandidateAlpha.model_validate(
                {
                    "idea_id": idea.idea_id,
                    "simulation_settings": {
                        "type": "REGULAR",
                        "settings": {
                            "instrumentType": idea.target.instrumentType,
                            "region": idea.target.region,
                            "universe": idea.target.universe,
                            "delay": idea.target.delay,
                            "decay": 15,
                            "neutralization": "SUBINDUSTRY",
                            "truncation": 0.08,
                            "maxTrade": "ON",
                            "pasteurization": "ON",
                            "testPeriod": "P1Y6M",
                            "unitHandling": "VERIFY",
                            "nanHandling": "OFF",
                            "language": "FASTEXPR",
                            "visualization": False,
                        },
                        "regular": expr,
                    },
                    "generation_notes": {
                        "used_fields": ["close"],
                        "used_operators": ["rank", "ts_delta", "log"],
                    },
                }
            )
            out.append(candidate)
        return out

    def _mutate_from_failures(self, candidates: list[CandidateAlpha], cards: list[ScoreCard]) -> list[CandidateAlpha]:
        by_idea = {candidate.idea_id: candidate for candidate in candidates}
        generated: list[CandidateAlpha] = []

        for card in cards:
            if card.passed:
                continue

            # Alpha IDs do not directly map to ideas, so we mutate all ideas conservatively.
            for candidate in by_idea.values():
                generated.extend(
                    self.mutator.propose_mutations(
                        candidate,
                        card,
                        max_variants=3,
                        run_id="pipeline-cycle",
                        parent_alpha_id=card.alpha_id,
                    )
                )

        return generated
