"""Metadata sync workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..brain_api.metadata import (
    get_data_fields,
    get_datasets,
    get_operators,
    get_simulation_options,
    parse_simulation_allowed_values,
)
from ..constants import DEFAULT_META_DIR
from ..schemas import SimulationTarget
from ..storage.sqlite_store import MetadataStore
from ..utils.filesystem import utc_date, utc_now_iso, write_json


def _dated_path(meta_dir: Path, stem: str, date_tag: str, suffix: str = "json") -> Path:
    return meta_dir / f"{stem}_{date_tag}.{suffix}"


def sync_simulation_options(
    session: Any,
    store: MetadataStore,
    meta_dir: str | Path = DEFAULT_META_DIR,
) -> dict[str, Any]:
    """Sync OPTIONS /simulations payload and persist snapshots."""
    out_dir = Path(meta_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = get_simulation_options(session)
    allowed = parse_simulation_allowed_values(raw)

    date_tag = utc_date()
    write_json(out_dir / "simulations_options.json", {"date": date_tag, "allowed": allowed, "raw": raw})
    write_json(_dated_path(out_dir, "simulations_options", date_tag), {"allowed": allowed, "raw": raw})
    store.upsert_simulation_options(date_tag, {"allowed": allowed, "raw": raw})
    return {"allowed": allowed, "raw": raw}


def sync_operators(
    session: Any,
    store: MetadataStore,
    meta_dir: str | Path = DEFAULT_META_DIR,
) -> list[dict[str, Any]]:
    """Sync operators into JSON and SQLite."""
    out_dir = Path(meta_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    operators = get_operators(session)
    date_tag = utc_date()
    ts = utc_now_iso()

    write_json(_dated_path(out_dir, "operators", date_tag), operators)
    write_json(out_dir / "operators_latest.json", operators)
    store.upsert_operators(operators, fetched_at=ts)
    return operators


def sync_datasets(
    session: Any,
    store: MetadataStore,
    target: SimulationTarget,
    *,
    meta_dir: str | Path = DEFAULT_META_DIR,
    theme: str | None = None,
    search: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Sync datasets for target combination."""
    out_dir = Path(meta_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets = get_datasets(
        session,
        instrument_type=target.instrumentType,
        region=target.region,
        delay=target.delay,
        universe=target.universe,
        theme=theme,
        search=search,
        category=category,
    )
    date_tag = utc_date()
    ts = utc_now_iso()

    file_stem = f"datasets_{target.region}_{target.delay}_{target.universe}"
    write_json(_dated_path(out_dir, file_stem, date_tag), datasets)
    write_json(out_dir / f"{file_stem}_latest.json", datasets)

    store.upsert_datasets(
        datasets,
        region=target.region,
        delay=target.delay,
        universe=target.universe,
        fetched_at=ts,
    )
    return datasets


def sync_data_fields(
    session: Any,
    store: MetadataStore,
    target: SimulationTarget,
    *,
    dataset_ids: list[str] | None = None,
    field_type: str | None = None,
    search: str | None = None,
    meta_dir: str | Path = DEFAULT_META_DIR,
) -> list[dict[str, Any]]:
    """Sync data fields for target combination and optional dataset filters."""
    out_dir = Path(meta_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    ids = dataset_ids or [None]
    for dataset_id in ids:
        rows.extend(
            get_data_fields(
                session,
                instrument_type=target.instrumentType,
                region=target.region,
                delay=target.delay,
                universe=target.universe,
                dataset_id=dataset_id,
                field_type=field_type,
                search=search,
            )
        )

    # Deduplicate by field id.
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        field_id = row.get("id")
        if field_id:
            deduped[str(field_id)] = row
    out = list(deduped.values())

    date_tag = utc_date()
    ts = utc_now_iso()
    file_stem = f"data_fields_{target.region}_{target.delay}_{target.universe}"

    write_json(_dated_path(out_dir, file_stem, date_tag), out)
    write_json(out_dir / f"{file_stem}_latest.json", out)

    store.upsert_data_fields(
        out,
        region=target.region,
        delay=target.delay,
        universe=target.universe,
        fetched_at=ts,
    )
    return out


def sync_all_metadata(
    session: Any,
    store: MetadataStore,
    target: SimulationTarget,
    *,
    sync_fields: bool = True,
    max_field_datasets: int | None = 30,
    meta_dir: str | Path = DEFAULT_META_DIR,
) -> dict[str, int]:
    """Run metadata sync policy for options/operators/datasets/fields."""
    sync_simulation_options(session, store, meta_dir=meta_dir)
    operators = sync_operators(session, store, meta_dir=meta_dir)
    datasets = sync_datasets(session, store, target, meta_dir=meta_dir)

    field_count = 0
    if sync_fields:
        dataset_ids = [str(row["id"]) for row in datasets if row.get("id")]
        if max_field_datasets is not None:
            dataset_ids = dataset_ids[:max_field_datasets]
        fields = sync_data_fields(session, store, target, dataset_ids=dataset_ids, meta_dir=meta_dir)
        field_count = len(fields)

    return {
        "operators": len(operators),
        "datasets": len(datasets),
        "data_fields": field_count,
    }
