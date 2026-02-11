"""FastAPI app for Brain Terminal live event streaming."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from ..config import AppConfig
from ..generation.budget import (
    build_budget_console_payload,
    build_kpi_payload,
    build_reactor_status_payload,
    load_llm_budget,
)
from ..runtime.event_bus import EventBus
from ..storage.sqlite_store import MetadataStore
from ..utils.filesystem import utc_now_iso


def create_app(
    *,
    store: MetadataStore | None = None,
    event_bus: EventBus | None = None,
    poll_interval_sec: float = 0.5,
) -> FastAPI:
    config = AppConfig()
    sqlite_store = store or MetadataStore(config.paths.db_path)
    bus = event_bus or EventBus(store=sqlite_store)
    llm_budget = load_llm_budget("configs/llm_budget.json")

    app = FastAPI(title="Brain Agent Live Stream", version="0.1.0")
    app.state.store = sqlite_store
    app.state.event_bus = bus
    reactor_hud_path = Path("docs/artifacts/step-20/reactor_hud.html")
    neural_lab_path = Path("docs/artifacts/step-21/neural_genesis_lab.html")
    control_jobs: dict[str, dict[str, Any]] = {}
    control_jobs_lock = Lock()

    @dataclass(frozen=True)
    class ControlActionSpec:
        action: str
        description: str
        template: dict[str, Any]

    action_specs = [
        ControlActionSpec(
            action="run-quick-validation-loop",
            description="One-click flow: idea -> retrieval -> validation-loop",
            template={
                "input": "docs/artifacts/step-08/ideaspec.example.json",
                "llm_provider": "mock",
                "knowledge_pack_dir": "data/meta/index",
                "skip_simulation": False,
                "max_repair_attempts": 3,
                "run_id": "",
                "work_dir": "/tmp/brain_ui_jobs",
            },
        ),
        ControlActionSpec(
            action="build-retrieval-pack",
            description="Build retrieval pack from IdeaSpec JSON",
            template={
                "idea": "docs/artifacts/step-08/ideaspec.example.json",
                "output": "/tmp/retrieval_pack_ui.json",
            },
        ),
        ControlActionSpec(
            action="build-knowledge-pack",
            description="Build FastExpr knowledge packs",
            template={
                "output_dir": "data/meta/index",
            },
        ),
        ControlActionSpec(
            action="run-idea-agent",
            description="Run Idea Researcher",
            template={
                "input": "docs/artifacts/step-08/ideaspec.example.json",
                "llm_provider": "mock",
                "output": "/tmp/idea_out_ui.json",
            },
        ),
        ControlActionSpec(
            action="run-alpha-maker",
            description="Run Alpha Maker",
            template={
                "idea": "/tmp/idea_out_ui.json",
                "retrieval_pack": "/tmp/retrieval_pack_ui.json",
                "knowledge_pack_dir": "data/meta/index",
                "llm_provider": "mock",
                "output": "/tmp/candidate_alpha_ui.json",
            },
        ),
        ControlActionSpec(
            action="run-validation-loop",
            description="Run validation-first repair loop",
            template={
                "idea": "/tmp/idea_out_ui.json",
                "retrieval_pack": "/tmp/retrieval_pack_ui.json",
                "knowledge_pack_dir": "data/meta/index",
                "llm_provider": "mock",
                "skip_simulation": False,
                "max_repair_attempts": 3,
                "output": "/tmp/validated_candidates_ui.json",
                "report_output": "/tmp/validation_report_ui.json",
            },
        ),
    ]
    action_map = {spec.action: spec for spec in action_specs}

    def _now() -> str:
        return utc_now_iso()

    def _safe_tail(text: str, *, max_chars: int = 20000) -> str:
        value = str(text or "")
        if len(value) <= max_chars:
            return value
        return value[-max_chars:]

    def _parse_json_from_output(text: str) -> dict[str, Any] | list[Any] | None:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        for line in reversed(lines):
            if not line.startswith("{") and not line.startswith("["):
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, (dict, list)):
                return payload
        return None

    def _control_run_id(action: str, params: dict[str, Any], job_id: str) -> str:
        raw = params.get("run_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
        return f"control-{action}-{job_id[:8]}"

    def _control_idea_id(params: dict[str, Any]) -> str:
        raw = params.get("idea_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
        return "control"

    def _publish_control_event(
        *,
        event_type: str,
        action: str,
        job_id: str,
        run_id: str,
        idea_id: str,
        severity: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        bus.publish(
            event_type=event_type,
            run_id=run_id,
            idea_id=idea_id,
            stage="control",
            message=message,
            severity=severity,
            payload={
                "job_id": job_id,
                "action": action,
                **(payload or {}),
            },
        )

    def _set_job(job_id: str, **updates: Any) -> dict[str, Any]:
        with control_jobs_lock:
            row = dict(control_jobs.get(job_id) or {})
            row.update(updates)
            control_jobs[job_id] = row
            return dict(row)

    def _get_job(job_id: str) -> dict[str, Any] | None:
        with control_jobs_lock:
            row = control_jobs.get(job_id)
            return dict(row) if isinstance(row, dict) else None

    def _list_jobs(*, limit: int = 50) -> list[dict[str, Any]]:
        with control_jobs_lock:
            rows = list(control_jobs.values())
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 500))]

    def _cli_env() -> dict[str, str]:
        env = dict(os.environ)
        current = str(env.get("PYTHONPATH") or "")
        chunks = [item for item in current.split(os.pathsep) if item]
        if "src" not in chunks:
            chunks.insert(0, "src")
        env["PYTHONPATH"] = os.pathsep.join(chunks)
        return env

    def _require_str(params: dict[str, Any], key: str, *, action: str) -> str:
        value = params.get(key)
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"Missing required param '{key}' for action '{action}'")
        return text

    def _append_opt(cmd: list[str], flag: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        cmd.extend([flag, text])

    def _append_flag(cmd: list[str], flag: str, enabled: Any) -> None:
        if bool(enabled):
            cmd.append(flag)

    def _build_cli_command(action: str, params: dict[str, Any]) -> list[str]:
        cmd = [sys.executable, "-m", "brain_agent.cli", action]
        if action == "build-retrieval-pack":
            _append_opt(cmd, "--idea", _require_str(params, "idea", action=action))
            _append_opt(cmd, "--query", params.get("query"))
            _append_opt(cmd, "--meta-dir", params.get("meta_dir"))
            _append_opt(cmd, "--budget-config", params.get("budget_config"))
            _append_opt(cmd, "--output", params.get("output"))
            return cmd

        if action == "build-knowledge-pack":
            _append_opt(cmd, "--output-dir", params.get("output_dir"))
            _append_opt(cmd, "--meta-dir", params.get("meta_dir"))
            return cmd

        if action == "run-idea-agent":
            _append_opt(cmd, "--input", _require_str(params, "input", action=action))
            _append_opt(cmd, "--raw-output", params.get("raw_output"))
            _append_opt(cmd, "--run-id", params.get("run_id"))
            _append_opt(cmd, "--max-regenerations", params.get("max_regenerations"))
            _append_opt(cmd, "--meta-dir", params.get("meta_dir"))
            _append_opt(cmd, "--llm-budget-config", params.get("llm_budget_config"))
            _append_opt(cmd, "--llm-provider", params.get("llm_provider"))
            _append_opt(cmd, "--llm-model", params.get("llm_model"))
            _append_opt(cmd, "--reasoning-effort", params.get("reasoning_effort"))
            _append_opt(cmd, "--verbosity", params.get("verbosity"))
            _append_opt(cmd, "--reasoning-summary", params.get("reasoning_summary"))
            _append_opt(cmd, "--max-output-tokens", params.get("max_output_tokens"))
            _append_opt(cmd, "--output", params.get("output"))
            return cmd

        if action == "run-alpha-maker":
            _append_opt(cmd, "--idea", _require_str(params, "idea", action=action))
            _append_opt(cmd, "--retrieval-pack", _require_str(params, "retrieval_pack", action=action))
            _append_opt(cmd, "--knowledge-pack-dir", params.get("knowledge_pack_dir"))
            _append_opt(cmd, "--raw-output", params.get("raw_output"))
            _append_opt(cmd, "--run-id", params.get("run_id"))
            _append_opt(cmd, "--max-regenerations", params.get("max_regenerations"))
            _append_opt(cmd, "--meta-dir", params.get("meta_dir"))
            _append_opt(cmd, "--llm-budget-config", params.get("llm_budget_config"))
            _append_opt(cmd, "--llm-provider", params.get("llm_provider"))
            _append_opt(cmd, "--llm-model", params.get("llm_model"))
            _append_opt(cmd, "--reasoning-effort", params.get("reasoning_effort"))
            _append_opt(cmd, "--verbosity", params.get("verbosity"))
            _append_opt(cmd, "--reasoning-summary", params.get("reasoning_summary"))
            _append_opt(cmd, "--max-output-tokens", params.get("max_output_tokens"))
            _append_opt(cmd, "--output", params.get("output"))
            return cmd

        if action == "run-validation-loop":
            _append_opt(cmd, "--idea", _require_str(params, "idea", action=action))
            _append_opt(cmd, "--retrieval-pack", _require_str(params, "retrieval_pack", action=action))
            _append_opt(cmd, "--knowledge-pack-dir", params.get("knowledge_pack_dir"))
            _append_opt(cmd, "--raw-output", params.get("raw_output"))
            _append_opt(cmd, "--run-id", params.get("run_id"))
            _append_opt(cmd, "--max-regenerations", params.get("max_regenerations"))
            _append_opt(cmd, "--max-repair-attempts", params.get("max_repair_attempts"))
            if params.get("stop_on_repeated_error") is True:
                cmd.append("--stop-on-repeated-error")
            if params.get("stop_on_repeated_error") is False:
                cmd.append("--no-stop-on-repeated-error")
            _append_flag(cmd, "--skip-simulation", params.get("skip_simulation"))
            _append_flag(cmd, "--skip-recordsets", params.get("skip_recordsets"))
            _append_opt(cmd, "--meta-dir", params.get("meta_dir"))
            _append_opt(cmd, "--llm-budget-config", params.get("llm_budget_config"))
            _append_opt(cmd, "--llm-provider", params.get("llm_provider"))
            _append_opt(cmd, "--llm-model", params.get("llm_model"))
            _append_opt(cmd, "--reasoning-effort", params.get("reasoning_effort"))
            _append_opt(cmd, "--verbosity", params.get("verbosity"))
            _append_opt(cmd, "--reasoning-summary", params.get("reasoning_summary"))
            _append_opt(cmd, "--max-output-tokens", params.get("max_output_tokens"))
            _append_opt(cmd, "--output", params.get("output"))
            _append_opt(cmd, "--report-output", params.get("report_output"))
            return cmd

        raise ValueError(f"Unsupported action: {action}")

    def _run_cli(command: list[str]) -> dict[str, Any]:
        proc = subprocess.run(
            command,
            cwd=str(Path.cwd()),
            env=_cli_env(),
            capture_output=True,
            text=True,
        )
        return {
            "return_code": int(proc.returncode),
            "stdout": str(proc.stdout or ""),
            "stderr": str(proc.stderr or ""),
            "parsed": _parse_json_from_output(proc.stdout),
            "command": list(command),
        }

    def _required_knowledge_pack_missing(directory: str | Path) -> bool:
        root = Path(directory)
        required = (
            "operator_signature_pack.json",
            "simulation_settings_allowed_pack.json",
            "fastexpr_examples_pack.json",
            "fastexpr_visual_pack.json",
        )
        return any(not (root / name).exists() for name in required)

    def _run_quick_validation_loop(job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        run_id = _control_run_id("run-quick-validation-loop", params, job_id)
        work_root = Path(str(params.get("work_dir") or "/tmp/brain_ui_jobs"))
        work_dir = work_root / run_id
        work_dir.mkdir(parents=True, exist_ok=True)

        llm_provider = str(params.get("llm_provider") or "mock")
        llm_model = str(params.get("llm_model") or "gpt-5.2")
        input_path = _require_str(params, "input", action="run-quick-validation-loop")
        knowledge_pack_dir = str(params.get("knowledge_pack_dir") or "data/meta/index")
        max_repair_attempts = int(params.get("max_repair_attempts") or 3)
        skip_simulation = bool(params.get("skip_simulation", False))

        idea_path = str(work_dir / "idea_out.json")
        retrieval_path = str(work_dir / "retrieval_pack.json")
        validated_out = str(work_dir / "validated_candidates.json")
        report_out = str(work_dir / "validation_report.json")

        step_results: list[dict[str, Any]] = []

        cmd_idea = _build_cli_command(
            "run-idea-agent",
            {
                "input": input_path,
                "run_id": run_id,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "output": idea_path,
                "verbosity": params.get("verbosity") or "low",
                "reasoning_summary": params.get("reasoning_summary") or "concise",
                "max_output_tokens": params.get("max_output_tokens") or 1200,
                "max_regenerations": params.get("max_regenerations") or 1,
            },
        )
        outcome = _run_cli(cmd_idea)
        step_results.append({"step": "run-idea-agent", **outcome})
        if outcome["return_code"] != 0:
            return {
                "return_code": outcome["return_code"],
                "stdout": outcome["stdout"],
                "stderr": outcome["stderr"],
                "parsed": outcome.get("parsed"),
                "command": ["run-quick-validation-loop"],
                "steps": step_results,
                "run_id": run_id,
            }

        cmd_retrieval = _build_cli_command(
            "build-retrieval-pack",
            {
                "idea": idea_path,
                "output": retrieval_path,
            },
        )
        outcome = _run_cli(cmd_retrieval)
        step_results.append({"step": "build-retrieval-pack", **outcome})
        if outcome["return_code"] != 0:
            return {
                "return_code": outcome["return_code"],
                "stdout": outcome["stdout"],
                "stderr": outcome["stderr"],
                "parsed": outcome.get("parsed"),
                "command": ["run-quick-validation-loop"],
                "steps": step_results,
                "run_id": run_id,
            }

        if _required_knowledge_pack_missing(knowledge_pack_dir):
            cmd_knowledge = _build_cli_command(
                "build-knowledge-pack",
                {"output_dir": knowledge_pack_dir},
            )
            outcome = _run_cli(cmd_knowledge)
            step_results.append({"step": "build-knowledge-pack", **outcome})
            if outcome["return_code"] != 0:
                return {
                    "return_code": outcome["return_code"],
                    "stdout": outcome["stdout"],
                    "stderr": outcome["stderr"],
                    "parsed": outcome.get("parsed"),
                    "command": ["run-quick-validation-loop"],
                    "steps": step_results,
                    "run_id": run_id,
                }

        cmd_validation = _build_cli_command(
            "run-validation-loop",
            {
                "idea": idea_path,
                "retrieval_pack": retrieval_path,
                "knowledge_pack_dir": knowledge_pack_dir,
                "run_id": run_id,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "max_repair_attempts": max_repair_attempts,
                "skip_simulation": skip_simulation,
                "output": validated_out,
                "report_output": report_out,
                "verbosity": params.get("verbosity") or "low",
                "reasoning_summary": params.get("reasoning_summary") or "concise",
                "max_output_tokens": params.get("max_output_tokens") or 1200,
                "max_regenerations": params.get("max_regenerations") or 1,
            },
        )
        outcome = _run_cli(cmd_validation)
        step_results.append({"step": "run-validation-loop", **outcome})
        return {
            "return_code": outcome["return_code"],
            "stdout": outcome["stdout"],
            "stderr": outcome["stderr"],
            "parsed": outcome.get("parsed"),
            "command": ["run-quick-validation-loop"],
            "steps": step_results,
            "run_id": run_id,
            "artifacts": {
                "work_dir": str(work_dir),
                "idea": idea_path,
                "retrieval_pack": retrieval_path,
                "validated_candidates": validated_out,
                "report": report_out,
                "knowledge_pack_dir": knowledge_pack_dir,
            },
        }

    def _run_control_job_sync(job_id: str, action: str, params: dict[str, Any]) -> None:
        run_id = _control_run_id(action, params, job_id)
        idea_id = _control_idea_id(params)
        _set_job(job_id, status="running", started_at=_now(), run_id=run_id, idea_id=idea_id)
        _publish_control_event(
            event_type="control.job_started",
            action=action,
            job_id=job_id,
            run_id=run_id,
            idea_id=idea_id,
            severity="info",
            message=f"Control job started: {action}",
        )

        try:
            if action == "run-quick-validation-loop":
                outcome = _run_quick_validation_loop(job_id, params)
            else:
                command = _build_cli_command(action, params)
                outcome = _run_cli(command)
            raw_return_code = outcome.get("return_code")
            return_code = int(raw_return_code) if raw_return_code is not None else 1
            parsed = outcome.get("parsed")
            parsed_obj = parsed if isinstance(parsed, dict) else {}
            result_run_id = str(parsed_obj.get("run_id") or run_id)

            status = "completed" if return_code == 0 else "failed"
            _set_job(
                job_id,
                status=status,
                finished_at=_now(),
                return_code=return_code,
                command=outcome.get("command"),
                stdout_tail=_safe_tail(str(outcome.get("stdout") or "")),
                stderr_tail=_safe_tail(str(outcome.get("stderr") or "")),
                result=parsed,
                steps=outcome.get("steps"),
                artifacts=outcome.get("artifacts"),
            )
            _publish_control_event(
                event_type="control.job_completed" if return_code == 0 else "control.job_failed",
                action=action,
                job_id=job_id,
                run_id=result_run_id,
                idea_id=idea_id,
                severity="info" if return_code == 0 else "error",
                message=f"Control job {status}: {action}",
                payload={
                    "return_code": return_code,
                    "result": parsed_obj,
                    "artifacts": outcome.get("artifacts") if isinstance(outcome.get("artifacts"), dict) else {},
                },
            )
        except Exception as exc:
            _set_job(
                job_id,
                status="failed",
                finished_at=_now(),
                return_code=1,
                stderr_tail=_safe_tail(str(exc)),
            )
            _publish_control_event(
                event_type="control.job_failed",
                action=action,
                job_id=job_id,
                run_id=run_id,
                idea_id=idea_id,
                severity="error",
                message=f"Control job failed: {action}",
                payload={"error": str(exc)},
            )

    async def _run_control_job_async(job_id: str, action: str, params: dict[str, Any]) -> None:
        await asyncio.to_thread(_run_control_job_sync, job_id, action, params)

    def _payload_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row["payload"] for row in records if isinstance(row.get("payload"), dict)]

    def _latest_run_id(*, limit: int = 500) -> str | None:
        records = sqlite_store.list_event_records(limit=limit)
        for row in reversed(records):
            payload = row.get("payload")
            event = payload if isinstance(payload, dict) else {}
            run_id = str(event.get("run_id") or "").strip()
            if run_id and run_id != "legacy-run":
                return run_id
        return None

    def _reactor_envelope(run_id: str, *, limit: int, all_limit: int) -> dict[str, Any]:
        run_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=limit)
        all_records = sqlite_store.list_event_records(limit=all_limit)
        payload = build_reactor_status_payload(
            run_id=run_id,
            run_events=_payload_events(run_records),
            all_events=_payload_events(all_records),
            budget=llm_budget,
        )
        return {
            "event_type": "reactor.status",
            "run_id": run_id,
            "idea_id": "system",
            "stage": "budget",
            "message": "Reactor status snapshot",
            "severity": "info",
            "created_at": utc_now_iso(),
            "payload": payload,
        }

    def _validation_kpi_payload(run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        attempts: dict[int, dict[str, int]] = {}
        summary = {
            "runs": 0,
            "final_passed": 0,
            "final_failed": 0,
            "retrieval_expanded": 0,
        }
        for event in events:
            event_type = str(event.get("event_type") or "")
            payload = event.get("payload")
            detail = payload if isinstance(payload, dict) else {}
            attempt_raw = detail.get("attempt")
            try:
                attempt = int(attempt_raw) if attempt_raw is not None else 0
            except Exception:
                attempt = 0

            if event_type in {"validation.failed", "validation.retry_failed"}:
                row = attempts.setdefault(attempt, {"passed": 0, "failed": 0})
                row["failed"] += 1
            elif event_type in {"validation.passed", "validation.retry_passed"}:
                row = attempts.setdefault(attempt, {"passed": 0, "failed": 0})
                row["passed"] += 1

            if event_type == "validation.retrieval_expanded":
                summary["retrieval_expanded"] += 1
            elif event_type == "run.summary":
                summary["runs"] += 1
                if bool(detail.get("validation_passed")):
                    summary["final_passed"] += 1
                else:
                    summary["final_failed"] += 1

        attempt_rows = []
        for attempt in sorted(attempts):
            row = attempts[attempt]
            total = row["passed"] + row["failed"]
            pass_rate = (row["passed"] / total) if total > 0 else 0.0
            attempt_rows.append(
                {
                    "attempt": attempt,
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "total": total,
                    "pass_rate": round(pass_rate, 4),
                }
            )
        return {
            "run_id": run_id,
            "attempts": attempt_rows,
            "summary": summary,
        }

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/ui/reactor", response_model=None)
    def reactor_hud() -> Any:
        if not reactor_hud_path.exists():
            return {"ok": False, "error": f"hud_not_found:{reactor_hud_path}"}
        return FileResponse(reactor_hud_path)

    @app.get("/ui/neural-lab", response_model=None)
    def neural_lab_hud() -> Any:
        if not neural_lab_path.exists():
            return {"ok": False, "error": f"hud_not_found:{neural_lab_path}"}
        return FileResponse(neural_lab_path)

    @app.get("/api/events/recent")
    def recent_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        records = sqlite_store.list_event_records(limit=limit)
        return {
            "count": len(records),
            "events": [row["payload"] for row in records],
        }

    @app.get("/api/runs/{run_id}/budget")
    def run_budget(run_id: str, limit: int = Query(default=2000, ge=1, le=10000)) -> dict[str, Any]:
        run_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=limit)
        all_records = sqlite_store.list_event_records(limit=min(5000, max(500, limit)))
        run_events = [row["payload"] for row in run_records if isinstance(row.get("payload"), dict)]
        all_events = [row["payload"] for row in all_records if isinstance(row.get("payload"), dict)]
        return build_budget_console_payload(
            run_id=run_id,
            run_events=run_events,
            all_events=all_events,
            budget=llm_budget,
        )

    @app.get("/api/runs/{run_id}/kpi")
    def run_kpi(run_id: str, limit: int = Query(default=2000, ge=1, le=10000)) -> dict[str, Any]:
        run_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=limit)
        run_events = [row["payload"] for row in run_records if isinstance(row.get("payload"), dict)]
        return build_kpi_payload(
            run_id=run_id,
            run_events=run_events,
            budget=llm_budget,
        )

    @app.get("/api/runs/{run_id}/validation_kpi")
    def run_validation_kpi(run_id: str, limit: int = Query(default=2000, ge=1, le=10000)) -> dict[str, Any]:
        run_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=limit)
        run_events = [row["payload"] for row in run_records if isinstance(row.get("payload"), dict)]
        return _validation_kpi_payload(run_id, run_events)

    @app.get("/api/runs/{run_id}/reactor_status")
    def run_reactor_status(
        run_id: str,
        limit: int = Query(default=2000, ge=1, le=10000),
        all_limit: int = Query(default=5000, ge=200, le=20000),
    ) -> dict[str, Any]:
        run_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=limit)
        all_records = sqlite_store.list_event_records(limit=all_limit)
        run_events = [row["payload"] for row in run_records if isinstance(row.get("payload"), dict)]
        all_events = [row["payload"] for row in all_records if isinstance(row.get("payload"), dict)]
        return build_reactor_status_payload(
            run_id=run_id,
            run_events=run_events,
            all_events=all_events,
            budget=llm_budget,
        )

    @app.get("/api/control/actions")
    def control_actions() -> dict[str, Any]:
        return {
            "actions": [
                {
                    "action": spec.action,
                    "description": spec.description,
                    "template": spec.template,
                }
                for spec in action_specs
            ]
        }

    @app.post("/api/control/jobs")
    async def control_enqueue(payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        if not action:
            raise HTTPException(status_code=400, detail="Missing action")
        if action not in action_map:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

        params_raw = payload.get("params")
        params = params_raw if isinstance(params_raw, dict) else {}

        job_id = uuid4().hex
        run_id = _control_run_id(action, params, job_id)
        idea_id = _control_idea_id(params)
        created_at = _now()
        row = {
            "job_id": job_id,
            "action": action,
            "params": params,
            "status": "queued",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "run_id": run_id,
            "idea_id": idea_id,
            "return_code": None,
            "result": None,
            "command": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "steps": [],
            "artifacts": {},
        }
        _set_job(job_id, **{key: value for key, value in row.items() if key != "job_id"})
        _publish_control_event(
            event_type="control.job_queued",
            action=action,
            job_id=job_id,
            run_id=run_id,
            idea_id=idea_id,
            severity="info",
            message=f"Control job queued: {action}",
        )
        asyncio.create_task(_run_control_job_async(job_id, action, params))
        return row

    @app.get("/api/control/jobs")
    def control_list_jobs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        rows = _list_jobs(limit=limit)
        return {
            "count": len(rows),
            "jobs": rows,
        }

    @app.get("/api/control/jobs/{job_id}")
    def control_get_job(job_id: str) -> dict[str, Any]:
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return row

    @app.websocket("/ws/live")
    async def ws_live(
        websocket: WebSocket,
        replay: int = Query(default=20, ge=0, le=500),
        run_id: str | None = Query(default=None),
        include_reactor: bool = Query(default=False),
        reactor_interval_sec: float = Query(default=1.0, ge=0.2, le=10.0),
        run_limit: int = Query(default=2000, ge=100, le=10000),
        all_limit: int = Query(default=5000, ge=500, le=20000),
    ) -> None:
        await websocket.accept()

        if run_id:
            replay_records = sqlite_store.list_event_records_for_run(run_id=run_id, limit=replay) if replay > 0 else []
        else:
            replay_records = sqlite_store.list_event_records(limit=replay) if replay > 0 else []

        last_id = 0
        for row in replay_records:
            last_id = max(last_id, int(row["id"]))
            await websocket.send_json(row["payload"])

        if last_id == 0:
            newest = sqlite_store.list_event_records(limit=1)
            if newest:
                last_id = int(newest[-1]["id"])

        last_reactor_sent = 0.0

        try:
            while True:
                batch = sqlite_store.list_event_records_since(last_id=last_id, limit=200)
                if batch:
                    for row in batch:
                        last_id = max(last_id, int(row["id"]))
                        payload = row.get("payload")
                        event = payload if isinstance(payload, dict) else {}
                        if run_id and str(event.get("run_id") or "") != run_id:
                            continue
                        await websocket.send_json(event)

                if include_reactor:
                    loop = asyncio.get_running_loop()
                    now = loop.time()
                    if now - last_reactor_sent >= float(reactor_interval_sec):
                        target_run_id = run_id or _latest_run_id(limit=all_limit)
                        if target_run_id:
                            await websocket.send_json(
                                _reactor_envelope(
                                    target_run_id,
                                    limit=run_limit,
                                    all_limit=all_limit,
                                )
                            )
                        last_reactor_sent = now
                await asyncio.sleep(max(0.05, float(poll_interval_sec)))
        except WebSocketDisconnect:
            return

    return app


app = create_app()
