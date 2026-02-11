"""Event bus utilities for run/stage telemetry and Brain Terminal streaming."""

from __future__ import annotations

from typing import Any, Callable

from ..schemas import AgentEventEnvelope
from ..storage.sqlite_store import MetadataStore
from ..utils.filesystem import utc_now_iso

EventSink = Callable[[dict[str, Any]], None]


class EventBus:
    """Best-effort event bus.

    Events are persisted to SQLite first-class event_log (when store is present),
    then forwarded to optional sinks. Any sink/store failure is swallowed so that
    the main pipeline cannot fail due to observability issues.
    """

    def __init__(self, *, store: MetadataStore | None = None) -> None:
        self.store = store
        self._sinks: list[EventSink] = []

    def register_sink(self, sink: EventSink) -> None:
        if sink not in self._sinks:
            self._sinks.append(sink)

    def remove_sink(self, sink: EventSink) -> None:
        self._sinks = [item for item in self._sinks if item is not sink]

    def publish(
        self,
        *,
        event_type: str,
        run_id: str,
        idea_id: str,
        stage: str,
        message: str,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        envelope = AgentEventEnvelope(
            event_type=event_type,
            run_id=run_id,
            idea_id=idea_id,
            stage=stage,
            message=message,
            severity=severity if severity in {"info", "warn", "error"} else "info",
            created_at=created_at or utc_now_iso(),
            payload=payload or {},
        )

        row = envelope.model_dump(mode="python")

        if self.store is not None:
            try:
                self.store.append_event(event_type, row)
            except Exception:
                pass

        for sink in list(self._sinks):
            try:
                sink(row)
            except Exception:
                continue

        return row
