"""Metadata sync workflows."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
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
from .organize import build_metadata_indexes


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
    wait_on_rate_limit: bool = True,
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
        wait_on_rate_limit=wait_on_rate_limit,
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
    wait_on_rate_limit: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Sync data fields for target combination and optional dataset filters."""
    out_dir = Path(meta_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    date_tag = utc_date()
    file_stem = f"data_fields_{target.region}_{target.delay}_{target.universe}"
    latest_path = out_dir / f"{file_stem}_latest.json"
    dated_path = _dated_path(out_dir, file_stem, date_tag)
    progress_path = out_dir / f"{file_stem}_progress.json"

    deduped: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    if dataset_ids is None:
        ids: list[str | None] = [None]
        dataset_mode = "all"
    else:
        ids = list(dataset_ids)
        dataset_mode = "subset"
    total_datasets = len(ids)
    page_count = 0
    raw_count = 0
    current_total_hint = 0
    current_dataset_id: str | None = None
    checkpoint_interval_pages = 5

    def write_progress(*, status: str, dataset_index: int, final: bool) -> None:
        write_json(
            progress_path,
            {
                "status": status,
                "final": final,
                "updated_at": utc_now_iso(),
                "target": {
                    "instrumentType": target.instrumentType,
                    "region": target.region,
                    "delay": target.delay,
                    "universe": target.universe,
                },
                "dataset_mode": dataset_mode,
                "dataset_cursor": {
                    "index": dataset_index,
                    "total": total_datasets,
                    "id": current_dataset_id,
                },
                "progress": {
                    "pages": page_count,
                    "raw_rows_seen": raw_count,
                    "unique_fields": len(deduped),
                    "page_total_hint": current_total_hint,
                },
                "errors": errors,
            },
        )

    def flush_checkpoint(*, dataset_index: int, force_log: bool = False) -> None:
        write_json(latest_path, list(deduped.values()))
        write_progress(status="running", dataset_index=dataset_index, final=False)
        if force_log:
            print(
                f"[SYNC] /data-fields progress: datasets={dataset_index}/{total_datasets}, "
                f"pages={page_count}, unique={len(deduped)}, raw_rows={raw_count}",
                file=sys.stderr,
                flush=True,
            )

    for idx, dataset_id in enumerate(ids, start=1):
        current_dataset_id = str(dataset_id) if dataset_id is not None else None
        write_progress(status="running", dataset_index=idx, final=False)

        def on_page(page_rows: list[dict[str, Any]], _offset: int, total_count: int) -> None:
            nonlocal page_count, raw_count, current_total_hint
            page_count += 1
            raw_count += len(page_rows)
            current_total_hint = total_count
            for row in page_rows:
                field_id = row.get("id")
                if field_id:
                    deduped[str(field_id)] = row
            if page_rows:
                store.upsert_data_fields(
                    page_rows,
                    region=target.region,
                    delay=target.delay,
                    universe=target.universe,
                    fetched_at=utc_now_iso(),
                )
            if page_count == 1 or page_count % checkpoint_interval_pages == 0:
                flush_checkpoint(dataset_index=idx, force_log=True)

        try:
            get_data_fields(
                session,
                instrument_type=target.instrumentType,
                region=target.region,
                delay=target.delay,
                universe=target.universe,
                dataset_id=dataset_id,
                field_type=field_type,
                search=search,
                wait_on_rate_limit=wait_on_rate_limit,
                on_page=on_page,
                collect_results=False,
            )
        except KeyboardInterrupt:
            flush_checkpoint(dataset_index=idx, force_log=True)
            write_progress(status="interrupted", dataset_index=idx, final=False)
            raise
        except Exception as exc:
            errors.append(
                {
                    "dataset_id": str(dataset_id),
                    "error": str(exc),
                }
            )
            flush_checkpoint(dataset_index=idx, force_log=True)
            # 429 is usually account/API throttling. Keep already fetched data and stop early.
            if "429" in str(exc):
                break
            continue

    out = list(deduped.values())

    write_json(dated_path, out)
    write_json(latest_path, out)

    if errors:
        write_json(_dated_path(out_dir, f"{file_stem}_sync_errors", date_tag), errors)
        write_progress(status="partial_error", dataset_index=total_datasets, final=True)
    else:
        write_progress(status="completed", dataset_index=total_datasets, final=True)
    return out, errors


def sync_all_metadata(
    session: Any,
    store: MetadataStore,
    target: SimulationTarget,
    *,
    sync_fields: bool = True,
    max_field_datasets: int | None = None,
    meta_dir: str | Path = DEFAULT_META_DIR,
    wait_on_rate_limit: bool = True,
) -> dict[str, Any]:
    """Run metadata sync policy for options/operators/datasets/fields."""
    sync_simulation_options(session, store, meta_dir=meta_dir)
    operators = sync_operators(session, store, meta_dir=meta_dir)
    datasets = sync_datasets(session, store, target, meta_dir=meta_dir, wait_on_rate_limit=wait_on_rate_limit)

    field_count = 0
    field_error_count = 0
    field_expected_upper_bound = 0
    selected_dataset_ids: list[str] = []
    fields: list[dict[str, Any]] = []
    if sync_fields:
        if max_field_datasets is None:
            # Full sync mode: shard by all dataset ids to bypass API-wide page/count caps.
            # Some endpoints cap global /data-fields results around 10k rows.
            selected_dataset_ids = _select_dataset_ids_for_field_sync(
                datasets,
                max_field_datasets=None,
            )
            dataset_ids_for_fields = selected_dataset_ids
            field_sync_scope = "all_datasets"
        else:
            selected_dataset_ids = _select_dataset_ids_for_field_sync(
                datasets,
                max_field_datasets=max_field_datasets,
            )
            dataset_ids_for_fields = selected_dataset_ids
            field_sync_scope = "dataset_subset"
        field_expected_upper_bound = _sum_field_count_for_dataset_ids(
            datasets,
            dataset_ids_for_fields,
        )
        fields, errors = sync_data_fields(
            session,
            store,
            target,
            dataset_ids=dataset_ids_for_fields,
            meta_dir=meta_dir,
            wait_on_rate_limit=wait_on_rate_limit,
        )
        field_count = len(fields)
        field_error_count = len(errors)
    else:
        field_sync_scope = "skipped"

    index_summary = build_metadata_indexes(
        meta_dir=meta_dir,
        datasets=datasets,
        operators=operators,
        data_fields=fields,
    )

    return {
        "operators": len(operators),
        "datasets": len(datasets),
        "data_fields": field_count,
        "field_expected_upper_bound": field_expected_upper_bound,
        "data_field_errors": field_error_count,
        "field_dataset_ids_used": len(selected_dataset_ids),
        "field_sync_scope": field_sync_scope,
        "dataset_categories_indexed": index_summary.get("dataset_categories", 0),
        "dataset_subcategories_indexed": index_summary.get("dataset_subcategories", 0),
    }


def _select_dataset_ids_for_field_sync(
    datasets: list[dict[str, Any]],
    *,
    max_field_datasets: int | None,
) -> list[str]:
    """Select dataset ids for /data-fields sync with category diversity first."""
    dataset_rows = [row for row in datasets if row.get("id")]
    if not dataset_rows:
        return []

    ranked = sorted(dataset_rows, key=_dataset_quality_score, reverse=True)
    if max_field_datasets is None:
        return [str(row["id"]) for row in ranked]

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ranked:
        buckets[_category_id(row)].append(row)

    selected: list[str] = []
    cat_keys = sorted(buckets.keys())
    while len(selected) < max_field_datasets:
        progressed = False
        for cat_key in cat_keys:
            bucket = buckets[cat_key]
            if not bucket:
                continue
            selected.append(str(bucket.pop(0)["id"]))
            progressed = True
            if len(selected) >= max_field_datasets:
                break
        if not progressed:
            break
    return selected


def _dataset_quality_score(row: dict[str, Any]) -> float:
    coverage = _to_float(row.get("coverage"), 0.0)
    value_score = _to_float(row.get("valueScore"), 0.0)
    field_count = _to_float(row.get("fieldCount"), 0.0)
    user_count = _to_float(row.get("userCount"), 0.0)
    return value_score * 4.0 + coverage * 2.0 + field_count * 0.01 + user_count * 0.001


def _category_id(row: dict[str, Any]) -> str:
    category = row.get("category")
    if isinstance(category, dict):
        value = category.get("id")
        if value:
            return str(value)
    return "uncategorized"


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _sum_field_count_for_dataset_ids(
    datasets: list[dict[str, Any]],
    dataset_ids: list[str] | None,
) -> int:
    selected = set(str(x) for x in dataset_ids) if dataset_ids is not None else None
    total = 0
    for row in datasets:
        ds_id = row.get("id")
        if ds_id is None:
            continue
        if selected is not None and str(ds_id) not in selected:
            continue
        count = _to_float(row.get("fieldCount"), 0.0)
        if count > 0:
            total += int(count)
    return total
