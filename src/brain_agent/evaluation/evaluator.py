"""Evaluator agent logic: filtering, ranking, and correlation dedupe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional heavy dependency
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover
    pd = None  # type: ignore[assignment]

from ..config import FilterPolicy
from ..runtime.event_bus import EventBus
from ..schemas import AlphaResult, ScoreCard, SummaryMetrics


@dataclass
class ClusterSelection:
    selected_alpha_ids: list[str]
    dropped_alpha_ids: list[str]
    corr_matrix: Any


class Evaluator:
    """Apply policy filters and produce ranked scorecards."""

    def __init__(
        self,
        policy: FilterPolicy | None = None,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        self.policy = policy or FilterPolicy()
        self.event_bus = event_bus

    def evaluate(
        self,
        results: list[AlphaResult],
        *,
        run_id: str | None = None,
        idea_id: str | None = None,
    ) -> list[ScoreCard]:
        """Build scorecards sorted by composite score."""
        cards: list[ScoreCard] = []
        for result in results:
            metrics = result.summary_metrics
            reasons = self._failure_reasons(metrics)
            passed = len(reasons) == 0
            score = self._score(metrics, passed)
            cards.append(
                ScoreCard(
                    alpha_id=result.alpha_id,
                    passed=passed,
                    score=score,
                    reasons=reasons,
                    metrics=metrics,
                )
            )

        ranked = sorted(cards, key=lambda x: x.score, reverse=True)
        self._emit_completed_event(
            run_id=run_id,
            idea_id=idea_id or _infer_idea_id(results),
            scorecards=ranked,
        )
        return ranked

    def _failure_reasons(self, metrics: SummaryMetrics) -> list[str]:
        reasons: list[str] = []

        if metrics.sharpe is None or metrics.sharpe < self.policy.min_sharpe:
            reasons.append(f"sharpe<{self.policy.min_sharpe}")

        if metrics.fitness is None or metrics.fitness < self.policy.min_fitness:
            reasons.append(f"fitness<{self.policy.min_fitness}")

        if metrics.turnover is None:
            reasons.append("turnover_missing")
        else:
            if metrics.turnover <= self.policy.min_turnover:
                reasons.append(f"turnover<={self.policy.min_turnover}")
            if metrics.turnover >= self.policy.max_turnover:
                reasons.append(f"turnover>={self.policy.max_turnover}")

        return reasons

    def _score(self, metrics: SummaryMetrics, passed: bool) -> float:
        sharpe = metrics.sharpe or 0.0
        fitness = metrics.fitness or 0.0
        turnover = metrics.turnover if metrics.turnover is not None else self.policy.max_turnover

        # Prefer high sharpe/fitness with moderate turnover.
        turnover_penalty = abs(turnover - 30.0) / 100.0
        base = sharpe * 0.55 + fitness * 0.45 - turnover_penalty

        if not passed:
            base -= 1.0
        return base

    def select_low_correlation(
        self,
        scorecards: list[ScoreCard],
        daily_pnl: dict[str, list[float] | Any],
        *,
        max_abs_corr: float | None = None,
    ) -> ClusterSelection:
        """Keep top-ranked representative per high-correlation cluster."""
        _require_pandas("select_low_correlation")
        threshold = max_abs_corr if max_abs_corr is not None else self.policy.max_abs_corr

        pnl_df = _build_pnl_matrix(daily_pnl)
        if pnl_df.empty or pnl_df.shape[1] <= 1:
            ids = [card.alpha_id for card in scorecards if card.alpha_id in pnl_df.columns or pnl_df.empty]
            return ClusterSelection(ids, [], pd.DataFrame())  # type: ignore[union-attr]

        corr = pnl_df.corr().fillna(0.0)
        rank = {card.alpha_id: i for i, card in enumerate(scorecards)}

        selected: list[str] = []
        dropped: list[str] = []
        for alpha_id in sorted(corr.columns, key=lambda x: rank.get(x, 10**9)):
            is_duplicate = False
            for winner in selected:
                if abs(float(corr.loc[alpha_id, winner])) > threshold:
                    is_duplicate = True
                    break
            if is_duplicate:
                dropped.append(alpha_id)
            else:
                selected.append(alpha_id)

        return ClusterSelection(selected, dropped, corr)

    def stability_from_yearly_stats(self, yearly_stats: pd.DataFrame) -> dict[str, float]:
        """Compute simple consistency stats for yearly metrics."""
        _require_pandas("stability_from_yearly_stats")
        if yearly_stats.empty:
            return {"years": 0, "sharpe_std": 0.0, "pnl_std": 0.0, "drawdown_min": 0.0}

        out = {
            "years": float(len(yearly_stats.index)),
            "sharpe_std": float(yearly_stats.get("sharpe", pd.Series(dtype=float)).std(ddof=0) or 0.0),
            "pnl_std": float(yearly_stats.get("pnl", pd.Series(dtype=float)).std(ddof=0) or 0.0),
            "drawdown_min": float(yearly_stats.get("drawdown", pd.Series(dtype=float)).min() or 0.0),
        }
        return out

    def _emit_completed_event(
        self,
        *,
        run_id: str | None,
        idea_id: str,
        scorecards: list[ScoreCard],
    ) -> None:
        if self.event_bus is None or not run_id:
            return

        passed = [card for card in scorecards if card.passed]
        payload = {
            "total": len(scorecards),
            "passed": len(passed),
            "failed": len(scorecards) - len(passed),
            "top_alpha_ids": [card.alpha_id for card in scorecards[:5]],
            "scorecards": [
                {
                    "alpha_id": card.alpha_id,
                    "passed": card.passed,
                    "score": card.score,
                    "reasons": card.reasons,
                    "metrics": card.metrics.model_dump(mode="python"),
                }
                for card in scorecards
            ],
        }
        self.event_bus.publish(
            event_type="evaluation.completed",
            run_id=run_id,
            idea_id=idea_id,
            stage="evaluation",
            message="Evaluation completed",
            severity="info",
            payload=payload,
        )


def _infer_idea_id(results: list[AlphaResult]) -> str:
    for result in results:
        idea_id = str(result.idea_id or "").strip()
        if idea_id:
            return idea_id
    return "system"


def _build_pnl_matrix(daily_pnl: dict[str, list[float] | Any]) -> pd.DataFrame:
    _require_pandas("_build_pnl_matrix")
    series_map: dict[str, Any] = {}
    for alpha_id, values in daily_pnl.items():
        if isinstance(values, pd.Series):  # type: ignore[union-attr]
            series_map[alpha_id] = values.reset_index(drop=True)
        else:
            series_map[alpha_id] = pd.Series(values)  # type: ignore[union-attr]

    if not series_map:
        return pd.DataFrame()  # type: ignore[union-attr]

    max_len = max(len(s) for s in series_map.values())
    padded = {k: s.reindex(range(max_len)) for k, s in series_map.items()}
    return pd.DataFrame(padded)  # type: ignore[union-attr]


def _require_pandas(feature_name: str) -> None:
    if pd is None:
        raise RuntimeError(f"pandas is required for {feature_name}")
