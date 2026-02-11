"""FastAPI app for Brain Terminal live event streaming."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
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

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/ui/reactor")
    def reactor_hud() -> FileResponse | dict[str, Any]:
        if not reactor_hud_path.exists():
            return {"ok": False, "error": f"hud_not_found:{reactor_hud_path}"}
        return FileResponse(reactor_hud_path)

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
