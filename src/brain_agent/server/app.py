"""FastAPI app for Brain Terminal live event streaming."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect

from ..config import AppConfig
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
