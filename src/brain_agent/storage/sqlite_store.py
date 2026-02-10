"""SQLite persistence for metadata and simulation artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..constants import DEFAULT_DB_PATH
from ..schemas import AlphaResult
from ..utils.filesystem import utc_now_iso


class MetadataStore:
    """SQLite-backed store for metadata, fingerprints, and results."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS operators (
                    name TEXT PRIMARY KEY,
                    category TEXT,
                    scope TEXT,
                    definition TEXT,
                    description TEXT,
                    level TEXT,
                    documentation TEXT,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    region TEXT,
                    delay INTEGER,
                    universe TEXT,
                    coverage REAL,
                    valueScore REAL,
                    fieldCount INTEGER,
                    alphaCount INTEGER,
                    userCount INTEGER,
                    themes TEXT,
                    fetched_at TEXT NOT NULL,
                    raw_json TEXT
                );

                CREATE TABLE IF NOT EXISTS data_fields (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    region TEXT,
                    delay INTEGER,
                    universe TEXT,
                    type TEXT,
                    description TEXT,
                    coverage REAL,
                    alphaCount INTEGER,
                    userCount INTEGER,
                    themes TEXT,
                    fetched_at TEXT NOT NULL,
                    raw_json TEXT
                );

                CREATE TABLE IF NOT EXISTS simulation_options (
                    snapshot_date TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS simulation_fingerprints (
                    fingerprint TEXT PRIMARY KEY,
                    idea_id TEXT,
                    expression TEXT,
                    normalized_expression TEXT,
                    settings_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alpha_results (
                    alpha_id TEXT PRIMARY KEY,
                    idea_id TEXT NOT NULL,
                    settings_fingerprint TEXT NOT NULL,
                    expression_fingerprint TEXT NOT NULL,
                    sharpe REAL,
                    fitness REAL,
                    turnover REAL,
                    drawdown REAL,
                    coverage REAL,
                    recordsets_saved TEXT,
                    created_at TEXT NOT NULL,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_simulation_options(self, snapshot_date: str, payload: dict[str, Any]) -> None:
        fetched_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO simulation_options(snapshot_date, payload_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(snapshot_date) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    fetched_at=excluded.fetched_at
                """,
                (snapshot_date, json.dumps(payload, ensure_ascii=False), fetched_at),
            )

    def upsert_operators(self, operators: list[dict[str, Any]], fetched_at: str | None = None) -> None:
        ts = fetched_at or utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO operators(name, category, scope, definition, description, level, documentation, fetched_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    scope=excluded.scope,
                    definition=excluded.definition,
                    description=excluded.description,
                    level=excluded.level,
                    documentation=excluded.documentation,
                    fetched_at=excluded.fetched_at
                """,
                [
                    (
                        row.get("name"),
                        row.get("category"),
                        _normalize_scope(row.get("scope")),
                        row.get("definition"),
                        row.get("description"),
                        row.get("level"),
                        row.get("documentation"),
                        ts,
                    )
                    for row in operators
                    if row.get("name")
                ],
            )

    def upsert_datasets(
        self,
        datasets: list[dict[str, Any]],
        *,
        region: str,
        delay: int,
        universe: str,
        fetched_at: str | None = None,
    ) -> None:
        ts = fetched_at or utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO datasets(
                    id, name, description, region, delay, universe,
                    coverage, valueScore, fieldCount, alphaCount, userCount, themes,
                    fetched_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    region=excluded.region,
                    delay=excluded.delay,
                    universe=excluded.universe,
                    coverage=excluded.coverage,
                    valueScore=excluded.valueScore,
                    fieldCount=excluded.fieldCount,
                    alphaCount=excluded.alphaCount,
                    userCount=excluded.userCount,
                    themes=excluded.themes,
                    fetched_at=excluded.fetched_at,
                    raw_json=excluded.raw_json
                """,
                [
                    (
                        row.get("id"),
                        row.get("name"),
                        row.get("description"),
                        row.get("region", region),
                        row.get("delay", delay),
                        row.get("universe", universe),
                        _as_float(row.get("coverage")),
                        _as_float(row.get("valueScore")),
                        _as_int(row.get("fieldCount")),
                        _as_int(row.get("alphaCount")),
                        _as_int(row.get("userCount")),
                        json.dumps(row.get("themes"), ensure_ascii=False) if row.get("themes") is not None else None,
                        ts,
                        json.dumps(row, ensure_ascii=False),
                    )
                    for row in datasets
                    if row.get("id")
                ],
            )

    def upsert_data_fields(
        self,
        fields: list[dict[str, Any]],
        *,
        region: str,
        delay: int,
        universe: str,
        fetched_at: str | None = None,
    ) -> None:
        ts = fetched_at or utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO data_fields(
                    id, dataset_id, region, delay, universe,
                    type, description, coverage, alphaCount, userCount, themes,
                    fetched_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    dataset_id=excluded.dataset_id,
                    region=excluded.region,
                    delay=excluded.delay,
                    universe=excluded.universe,
                    type=excluded.type,
                    description=excluded.description,
                    coverage=excluded.coverage,
                    alphaCount=excluded.alphaCount,
                    userCount=excluded.userCount,
                    themes=excluded.themes,
                    fetched_at=excluded.fetched_at,
                    raw_json=excluded.raw_json
                """,
                [
                    (
                        row.get("id"),
                        _dataset_id_from_row(row),
                        row.get("region", region),
                        row.get("delay", delay),
                        row.get("universe", universe),
                        row.get("type"),
                        row.get("description"),
                        _as_float(row.get("coverage")),
                        _as_int(row.get("alphaCount")),
                        _as_int(row.get("userCount")),
                        json.dumps(row.get("themes"), ensure_ascii=False) if row.get("themes") is not None else None,
                        ts,
                        json.dumps(row, ensure_ascii=False),
                    )
                    for row in fields
                    if row.get("id")
                ],
            )

    def has_fingerprint(self, fingerprint: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM simulation_fingerprints WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return row is not None

    def save_fingerprint(
        self,
        *,
        fingerprint: str,
        idea_id: str,
        expression: str,
        normalized_expression: str,
        settings: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO simulation_fingerprints(
                    fingerprint, idea_id, expression, normalized_expression, settings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    idea_id,
                    expression,
                    normalized_expression,
                    json.dumps(settings, ensure_ascii=False),
                    utc_now_iso(),
                ),
            )

    def save_alpha_result(self, result: AlphaResult) -> None:
        metrics = result.summary_metrics
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alpha_results(
                    alpha_id, idea_id, settings_fingerprint, expression_fingerprint,
                    sharpe, fitness, turnover, drawdown, coverage,
                    recordsets_saved, created_at, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alpha_id) DO UPDATE SET
                    idea_id=excluded.idea_id,
                    settings_fingerprint=excluded.settings_fingerprint,
                    expression_fingerprint=excluded.expression_fingerprint,
                    sharpe=excluded.sharpe,
                    fitness=excluded.fitness,
                    turnover=excluded.turnover,
                    drawdown=excluded.drawdown,
                    coverage=excluded.coverage,
                    recordsets_saved=excluded.recordsets_saved,
                    created_at=excluded.created_at,
                    raw_payload=excluded.raw_payload
                """,
                (
                    result.alpha_id,
                    result.idea_id,
                    result.settings_fingerprint,
                    result.expression_fingerprint,
                    metrics.sharpe,
                    metrics.fitness,
                    metrics.turnover,
                    metrics.drawdown,
                    metrics.coverage,
                    json.dumps(result.recordsets_saved, ensure_ascii=False),
                    result.created_at,
                    json.dumps(result.raw_payload, ensure_ascii=False),
                ),
            )

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO event_log(event_type, payload_json, created_at) VALUES (?, ?, ?)",
                (event_type, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
            )

    def list_operators(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM operators").fetchall()
        return [dict(row) for row in rows]

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM datasets").fetchall()
        return [dict(row) for row in rows]

    def list_data_fields(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM data_fields").fetchall()
        return [dict(row) for row in rows]


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _dataset_id_from_row(row: dict[str, Any]) -> str | None:
    dataset = row.get("dataset")
    if isinstance(dataset, dict):
        return dataset.get("id")
    if isinstance(row.get("dataset_id"), str):
        return row.get("dataset_id")
    return None


def _normalize_scope(scope: Any) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, list):
        return ",".join(str(x) for x in scope)
    return str(scope)
