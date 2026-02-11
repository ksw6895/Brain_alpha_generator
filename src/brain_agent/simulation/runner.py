"""Simulation runner with dedupe and persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..brain_api.simulations import get_alpha_recordsets, get_recordset, run_multi_simulation, run_single_simulation
from ..schemas import AlphaResult, CandidateAlpha, SummaryMetrics
from ..storage.sqlite_store import MetadataStore
from ..utils.expressions import normalize_expression
from ..utils.filesystem import utc_now_iso, write_json
from ..utils.fingerprints import canonical_json, fingerprint_settings_expression


class SimulationRunner:
    """Submit candidate alphas and persist results."""

    def __init__(
        self,
        session: Any,
        store: MetadataStore,
        *,
        fetch_recordsets: bool = True,
        recordset_dir: str = "data/recordsets",
    ) -> None:
        self.session = session
        self.store = store
        self.fetch_recordsets = fetch_recordsets
        self.recordset_dir = recordset_dir

    def run_candidate(self, candidate: CandidateAlpha) -> AlphaResult | None:
        """Run one candidate unless already simulated."""
        expression = _candidate_expression(candidate)
        settings = candidate.simulation_settings.model_dump(mode="python")
        normalized_expression = normalize_expression(expression)
        fp = fingerprint_settings_expression(settings, normalized_expression)

        if self.store.has_fingerprint(fp):
            self.store.append_event(
                "simulation_skipped_duplicate",
                {
                    "idea_id": candidate.idea_id,
                    "fingerprint": fp,
                    "run_id": f"simulation-{candidate.idea_id}",
                    "stage": "simulation",
                    "message": "Skipped duplicate candidate by fingerprint",
                    "severity": "info",
                },
            )
            return None

        alpha_payload = run_single_simulation(self.session, settings)
        result = self._build_result(candidate, alpha_payload, fp, normalized_expression)

        self.store.save_fingerprint(
            fingerprint=fp,
            idea_id=candidate.idea_id,
            expression=expression,
            normalized_expression=normalized_expression,
            settings=settings,
        )
        result.recordsets_saved = self._fetch_and_save_recordsets(result.alpha_id)
        self.store.save_alpha_result(result)
        return result

    def run_candidates_multi(self, candidates: list[CandidateAlpha]) -> list[AlphaResult]:
        """Run 2-10 candidates as multi-simulation when possible."""
        if not candidates:
            return []

        filtered: list[CandidateAlpha] = []
        payloads: list[dict[str, Any]] = []
        fingerprints: list[str] = []
        expressions: list[str] = []

        for candidate in candidates:
            expression = _candidate_expression(candidate)
            settings = candidate.simulation_settings.model_dump(mode="python")
            normalized_expression = normalize_expression(expression)
            fp = fingerprint_settings_expression(settings, normalized_expression)
            if self.store.has_fingerprint(fp):
                self.store.append_event(
                    "simulation_skipped_duplicate",
                    {
                        "idea_id": candidate.idea_id,
                        "fingerprint": fp,
                        "run_id": f"simulation-{candidate.idea_id}",
                        "stage": "simulation",
                        "message": "Skipped duplicate candidate by fingerprint",
                        "severity": "info",
                    },
                )
                continue
            filtered.append(candidate)
            payloads.append(settings)
            fingerprints.append(fp)
            expressions.append(normalized_expression)

        if not filtered:
            return []

        if len(filtered) == 1:
            single = self.run_candidate(filtered[0])
            return [single] if single else []

        alpha_payloads = run_multi_simulation(self.session, payloads)
        if len(alpha_payloads) != len(filtered):
            # Fallback to single mode when mapping is ambiguous.
            out: list[AlphaResult] = []
            for candidate in filtered:
                one = self.run_candidate(candidate)
                if one:
                    out.append(one)
            return out

        out: list[AlphaResult] = []
        for candidate, alpha_payload, fp, normalized in zip(filtered, alpha_payloads, fingerprints, expressions):
            result = self._build_result(candidate, alpha_payload, fp, normalized)
            self.store.save_fingerprint(
                fingerprint=fp,
                idea_id=candidate.idea_id,
                expression=_candidate_expression(candidate),
                normalized_expression=normalized,
                settings=candidate.simulation_settings.model_dump(mode="python"),
            )
            result.recordsets_saved = self._fetch_and_save_recordsets(result.alpha_id)
            self.store.save_alpha_result(result)
            out.append(result)

        return out

    def _build_result(
        self,
        candidate: CandidateAlpha,
        alpha_payload: dict[str, Any],
        settings_fingerprint: str,
        normalized_expression: str,
    ) -> AlphaResult:
        alpha_id = str(alpha_payload.get("id") or alpha_payload.get("alpha") or "")
        if not alpha_id:
            raise RuntimeError(f"Missing alpha id in payload: {alpha_payload}")

        metrics = _extract_metrics(alpha_payload)
        expression_fp = hashlib.sha256(normalized_expression.encode("utf-8")).hexdigest()

        result = AlphaResult(
            idea_id=candidate.idea_id,
            alpha_id=alpha_id,
            settings_fingerprint=settings_fingerprint,
            expression_fingerprint=expression_fp,
            summary_metrics=metrics,
            recordsets_saved=[],
            created_at=utc_now_iso(),
            raw_payload=alpha_payload,
        )

        self.store.append_event(
            "simulation_completed",
            {
                "idea_id": candidate.idea_id,
                "alpha_id": alpha_id,
                "metrics": metrics.model_dump(mode="python"),
                "run_id": f"simulation-{candidate.idea_id}",
                "stage": "simulation",
                "message": "Simulation completed",
                "severity": "info",
            },
        )
        return result

    def _fetch_and_save_recordsets(self, alpha_id: str) -> list[str]:
        if not self.fetch_recordsets:
            return []

        names = get_alpha_recordsets(self.session, alpha_id)
        saved: list[str] = []
        for name in names:
            try:
                payload = get_recordset(self.session, alpha_id, name)
            except Exception:
                continue
            write_json(
                _recordset_path(self.recordset_dir, alpha_id, name),
                payload,
            )
            saved.append(name)
        return saved


def _candidate_expression(candidate: CandidateAlpha) -> str:
    sim = candidate.simulation_settings
    if sim.type == "REGULAR":
        return sim.regular or ""
    return sim.combo or ""


def _extract_metrics(alpha_payload: dict[str, Any]) -> SummaryMetrics:
    is_payload = alpha_payload.get("is", {}) if isinstance(alpha_payload.get("is"), dict) else {}

    return SummaryMetrics(
        sharpe=_metric(is_payload, "sharpe"),
        fitness=_metric(is_payload, "fitness"),
        turnover=_metric(is_payload, "turnover"),
        drawdown=_metric(is_payload, "drawdown", "maxDrawdown"),
        coverage=_metric(is_payload, "coverage"),
    )


def _metric(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _recordset_path(base_dir: str, alpha_id: str, name: str) -> Path:
    safe_name = name.replace("/", "_")
    return Path(base_dir) / alpha_id / f"{safe_name}.json"


def fingerprint_for_candidate(candidate: CandidateAlpha) -> str:
    """Exported helper for dedupe checks and tests."""
    settings = candidate.simulation_settings.model_dump(mode="python")
    expression = normalize_expression(_candidate_expression(candidate))
    return fingerprint_settings_expression(settings, expression)


def canonical_payload_for_candidate(candidate: CandidateAlpha) -> str:
    """Exported helper for debugging canonical payload generation."""
    return canonical_json(candidate.simulation_settings.model_dump(mode="python"))
