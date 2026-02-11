"""Simulation runner with validation-aware queue events and persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..brain_api.simulations import (
    get_alpha_recordsets,
    get_recordset,
    run_multi_simulation,
    run_single_simulation,
)
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
        enforce_validation_gate: bool = False,
    ) -> None:
        self.session = session
        self.store = store
        self.fetch_recordsets = fetch_recordsets
        self.recordset_dir = recordset_dir
        self.enforce_validation_gate = bool(enforce_validation_gate)

    def run_candidate(
        self,
        candidate: CandidateAlpha,
        *,
        run_id: str | None = None,
        queue_payload: dict[str, Any] | None = None,
    ) -> AlphaResult | None:
        """Run one candidate unless blocked by validation gate or dedupe."""
        active_run_id = str(run_id or f"simulation-{candidate.idea_id}")
        expression = _candidate_expression(candidate)
        settings = _simulation_payload(candidate)
        normalized_expression = normalize_expression(expression)
        fp = fingerprint_settings_expression(settings, normalized_expression)

        if not self._validation_gate_allows(candidate):
            self.store.append_event(
                "simulation.blocked_validation",
                {
                    "idea_id": candidate.idea_id,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Candidate blocked because validation_passed != true",
                    "severity": "warn",
                    "payload": self._queue_meta(candidate, queue_payload),
                },
            )
            return None

        if self.store.has_fingerprint(fp):
            self.store.append_event(
                "simulation_skipped_duplicate",
                {
                    "idea_id": candidate.idea_id,
                    "fingerprint": fp,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Skipped duplicate candidate by fingerprint",
                    "severity": "info",
                    "payload": self._queue_meta(candidate, queue_payload),
                },
            )
            return None

        self.store.append_event(
            "simulation.enqueued",
            {
                "idea_id": candidate.idea_id,
                "run_id": active_run_id,
                "stage": "simulation",
                "message": "Candidate enqueued for simulation",
                "severity": "info",
                "payload": {
                    **self._queue_meta(candidate, queue_payload),
                    "fingerprint": fp,
                },
            },
        )
        self.store.append_event(
            "simulation.started",
            {
                "idea_id": candidate.idea_id,
                "run_id": active_run_id,
                "stage": "simulation",
                "message": "Simulation started",
                "severity": "info",
                "payload": {
                    **self._queue_meta(candidate, queue_payload),
                    "mode": "single",
                    "fingerprint": fp,
                },
            },
        )

        last_progress_sig = ""

        def progress_callback(progress_payload: dict[str, Any]) -> None:
            nonlocal last_progress_sig
            signature = canonical_json(progress_payload)
            if signature == last_progress_sig:
                return
            last_progress_sig = signature
            self.store.append_event(
                "simulation.progress",
                {
                    "idea_id": candidate.idea_id,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Simulation progress update",
                    "severity": "info",
                    "payload": {
                        "progress": _extract_progress_value(progress_payload),
                        "raw": progress_payload,
                    },
                },
            )

        alpha_payload = run_single_simulation(
            self.session,
            settings,
            progress_callback=progress_callback,
        )
        result = self._build_result(
            candidate,
            alpha_payload,
            fp,
            normalized_expression,
            run_id=active_run_id,
            queue_payload=queue_payload,
        )

        self.store.save_fingerprint(
            fingerprint=fp,
            idea_id=candidate.idea_id,
            expression=expression,
            normalized_expression=normalized_expression,
            settings=settings,
        )
        try:
            result.recordsets_saved = self._fetch_and_save_recordsets(result.alpha_id)
        except Exception as exc:
            self.store.append_event(
                "simulation.recordsets_unavailable",
                {
                    "idea_id": candidate.idea_id,
                    "alpha_id": result.alpha_id,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Recordset fetch skipped due to non-fatal error",
                    "severity": "warn",
                    "payload": {"error": str(exc)},
                },
            )
            result.recordsets_saved = []
        self.store.save_alpha_result(result)
        return result

    def run_candidates_multi(
        self,
        candidates: list[CandidateAlpha],
        *,
        run_id: str | None = None,
        queue_payload: dict[str, Any] | None = None,
    ) -> list[AlphaResult]:
        """Run 2-10 candidates as multi-simulation when possible."""
        if not candidates:
            return []

        active_run_id = str(run_id or f"simulation-{candidates[0].idea_id}")
        filtered: list[CandidateAlpha] = []
        payloads: list[dict[str, Any]] = []
        fingerprints: list[str] = []
        expressions: list[str] = []

        for candidate in candidates:
            expression = _candidate_expression(candidate)
            settings = _simulation_payload(candidate)
            normalized_expression = normalize_expression(expression)
            fp = fingerprint_settings_expression(settings, normalized_expression)
            if not self._validation_gate_allows(candidate):
                self.store.append_event(
                    "simulation.blocked_validation",
                    {
                        "idea_id": candidate.idea_id,
                        "run_id": active_run_id,
                        "stage": "simulation",
                        "message": "Candidate blocked because validation_passed != true",
                        "severity": "warn",
                        "payload": self._queue_meta(candidate, queue_payload),
                    },
                )
                continue
            if self.store.has_fingerprint(fp):
                self.store.append_event(
                    "simulation_skipped_duplicate",
                    {
                        "idea_id": candidate.idea_id,
                        "fingerprint": fp,
                        "run_id": active_run_id,
                        "stage": "simulation",
                        "message": "Skipped duplicate candidate by fingerprint",
                        "severity": "info",
                        "payload": self._queue_meta(candidate, queue_payload),
                    },
                )
                continue
            filtered.append(candidate)
            payloads.append(settings)
            fingerprints.append(fp)
            expressions.append(normalized_expression)
            self.store.append_event(
                "simulation.enqueued",
                {
                    "idea_id": candidate.idea_id,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Candidate enqueued for simulation",
                    "severity": "info",
                    "payload": {
                        **self._queue_meta(candidate, queue_payload),
                        "fingerprint": fp,
                    },
                },
            )

        if not filtered:
            return []

        if len(filtered) == 1:
            single = self.run_candidate(filtered[0], run_id=active_run_id, queue_payload=queue_payload)
            return [single] if single else []

        self.store.append_event(
            "simulation.started",
            {
                "idea_id": filtered[0].idea_id,
                "run_id": active_run_id,
                "stage": "simulation",
                "message": "Simulation started",
                "severity": "info",
                "payload": {
                    "mode": "multi",
                    "candidate_count": len(filtered),
                },
            },
        )

        last_progress_sig = ""

        def progress_callback(progress_payload: dict[str, Any]) -> None:
            nonlocal last_progress_sig
            signature = canonical_json(progress_payload)
            if signature == last_progress_sig:
                return
            last_progress_sig = signature
            self.store.append_event(
                "simulation.progress",
                {
                    "idea_id": filtered[0].idea_id,
                    "run_id": active_run_id,
                    "stage": "simulation",
                    "message": "Simulation progress update",
                    "severity": "info",
                    "payload": {
                        "progress": _extract_progress_value(progress_payload),
                        "raw": progress_payload,
                    },
                },
            )

        alpha_payloads = run_multi_simulation(
            self.session,
            payloads,
            progress_callback=progress_callback,
        )
        if len(alpha_payloads) != len(filtered):
            # Fallback to single mode when mapping is ambiguous.
            out: list[AlphaResult] = []
            for candidate in filtered:
                one = self.run_candidate(candidate, run_id=active_run_id, queue_payload=queue_payload)
                if one:
                    out.append(one)
            return out

        out: list[AlphaResult] = []
        for candidate, alpha_payload, fp, normalized in zip(filtered, alpha_payloads, fingerprints, expressions):
            result = self._build_result(
                candidate,
                alpha_payload,
                fp,
                normalized,
                run_id=active_run_id,
                queue_payload=queue_payload,
            )
            self.store.save_fingerprint(
                fingerprint=fp,
                idea_id=candidate.idea_id,
                expression=_candidate_expression(candidate),
                normalized_expression=normalized,
                settings=_simulation_payload(candidate),
            )
            try:
                result.recordsets_saved = self._fetch_and_save_recordsets(result.alpha_id)
            except Exception as exc:
                self.store.append_event(
                    "simulation.recordsets_unavailable",
                    {
                        "idea_id": candidate.idea_id,
                        "alpha_id": result.alpha_id,
                        "run_id": active_run_id,
                        "stage": "simulation",
                        "message": "Recordset fetch skipped due to non-fatal error",
                        "severity": "warn",
                        "payload": {"error": str(exc)},
                    },
                )
                result.recordsets_saved = []
            self.store.save_alpha_result(result)
            out.append(result)

        return out

    def _build_result(
        self,
        candidate: CandidateAlpha,
        alpha_payload: dict[str, Any],
        settings_fingerprint: str,
        normalized_expression: str,
        *,
        run_id: str,
        queue_payload: dict[str, Any] | None = None,
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

        payload = {
            "idea_id": candidate.idea_id,
            "alpha_id": alpha_id,
            "metrics": metrics.model_dump(mode="python"),
            "run_id": run_id,
            "stage": "simulation",
            "message": "Simulation completed",
            "severity": "info",
            "payload": {
                **self._queue_meta(candidate, queue_payload),
            },
        }
        # New dotted event name.
        self.store.append_event("simulation.completed", payload)
        # Backward-compatible alias.
        self.store.append_event("simulation_completed", payload)
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
            write_json(_recordset_path(self.recordset_dir, alpha_id, name), payload)
            saved.append(name)
        return saved

    def _validation_gate_allows(self, candidate: CandidateAlpha) -> bool:
        if not self.enforce_validation_gate:
            return True
        return bool(candidate.generation_notes.validation_passed)

    def _queue_meta(self, candidate: CandidateAlpha, queue_payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(queue_payload or {})
        payload.setdefault("candidate_lane", candidate.generation_notes.candidate_lane)
        payload.setdefault("validation_passed", candidate.generation_notes.validation_passed)
        payload.setdefault("validation_attempts", candidate.generation_notes.validation_attempts)
        return payload


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


def _extract_progress_value(payload: dict[str, Any]) -> float | None:
    for key in ("progress", "percent", "pct", "completion"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except Exception:
            continue
        if number > 1.0:
            return round(number / 100.0, 4)
        return round(number, 4)

    done = payload.get("childrenDone")
    total = payload.get("childrenTotal")
    if done is not None and total is not None:
        try:
            total_value = float(total)
            if total_value > 0:
                return round(float(done) / total_value, 4)
        except Exception:
            return None
    return None


def fingerprint_for_candidate(candidate: CandidateAlpha) -> str:
    """Exported helper for dedupe checks and tests."""
    settings = _simulation_payload(candidate)
    expression = normalize_expression(_candidate_expression(candidate))
    return fingerprint_settings_expression(settings, expression)


def canonical_payload_for_candidate(candidate: CandidateAlpha) -> str:
    """Exported helper for debugging canonical payload generation."""
    return canonical_json(_simulation_payload(candidate))


def _simulation_payload(candidate: CandidateAlpha) -> dict[str, Any]:
    """Build simulation payload while dropping null optional expression keys.

    Brain API may reject explicit null values for optional fields (e.g. selection/combo).
    """
    payload = candidate.simulation_settings.model_dump(mode="python", exclude_none=True)
    for key in ("regular", "selection", "combo"):
        if payload.get(key) is None:
            payload.pop(key, None)
    return payload
