"""FastAPI app for Brain Terminal live event streaming."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect

from ..config import AppConfig
from ..generation.budget import build_budget_console_payload, build_kpi_payload, load_llm_budget
from ..runtime.event_bus import EventBus
from ..storage.sqlite_store import MetadataStore


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

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

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

    @app.websocket("/ws/live")
    async def ws_live(
        websocket: WebSocket,
        replay: int = Query(default=20, ge=0, le=500),
    ) -> None:
        await websocket.accept()

        replay_records = sqlite_store.list_event_records(limit=replay) if replay > 0 else []
        last_id = 0
        for row in replay_records:
            last_id = max(last_id, int(row["id"]))
            await websocket.send_json(row["payload"])

        if last_id == 0:
            newest = sqlite_store.list_event_records(limit=1)
            if newest:
                last_id = int(newest[-1]["id"])

        try:
            while True:
                batch = sqlite_store.list_event_records_since(last_id=last_id, limit=200)
                if batch:
                    for row in batch:
                        last_id = max(last_id, int(row["id"]))
                        await websocket.send_json(row["payload"])
                await asyncio.sleep(max(0.05, float(poll_interval_sec)))
        except WebSocketDisconnect:
            return

    return app


app = create_app()
