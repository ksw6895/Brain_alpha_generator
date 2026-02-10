"""Evaluator agent logic: filtering, ranking, and correlation dedupe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..config import FilterPolicy
from ..schemas import AlphaResult, ScoreCard, SummaryMetrics


@dataclass
class ClusterSelection:
    selected_alpha_ids: list[str]
    dropped_alpha_ids: list[str]
    corr_matrix: pd.DataFrame


class Evaluator:
    """Apply policy filters and produce ranked scorecards."""

    def __init__(self, policy: FilterPolicy | None = None) -> None:
        self.policy = policy or FilterPolicy()

    def evaluate(self, results: list[AlphaResult]) -> list[ScoreCard]:
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

        return sorted(cards, key=lambda x: x.score, reverse=True)

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
        daily_pnl: dict[str, list[float] | pd.Series],
        *,
        max_abs_corr: float | None = None,
    ) -> ClusterSelection:
        """Keep top-ranked representative per high-correlation cluster."""
        threshold = max_abs_corr if max_abs_corr is not None else self.policy.max_abs_corr

        pnl_df = _build_pnl_matrix(daily_pnl)
        if pnl_df.empty or pnl_df.shape[1] <= 1:
            ids = [card.alpha_id for card in scorecards if card.alpha_id in pnl_df.columns or pnl_df.empty]
            return ClusterSelection(ids, [], pd.DataFrame())

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
        if yearly_stats.empty:
            return {"years": 0, "sharpe_std": 0.0, "pnl_std": 0.0, "drawdown_min": 0.0}

        out = {
            "years": float(len(yearly_stats.index)),
            "sharpe_std": float(yearly_stats.get("sharpe", pd.Series(dtype=float)).std(ddof=0) or 0.0),
            "pnl_std": float(yearly_stats.get("pnl", pd.Series(dtype=float)).std(ddof=0) or 0.0),
            "drawdown_min": float(yearly_stats.get("drawdown", pd.Series(dtype=float)).min() or 0.0),
        }
        return out


def _build_pnl_matrix(daily_pnl: dict[str, list[float] | pd.Series]) -> pd.DataFrame:
    series_map: dict[str, pd.Series] = {}
    for alpha_id, values in daily_pnl.items():
        if isinstance(values, pd.Series):
            series_map[alpha_id] = values.reset_index(drop=True)
        else:
            series_map[alpha_id] = pd.Series(values)

    if not series_map:
        return pd.DataFrame()

    max_len = max(len(s) for s in series_map.values())
    padded = {k: s.reindex(range(max_len)) for k, s in series_map.items()}
    return pd.DataFrame(padded)
