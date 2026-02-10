"""Metadata endpoints for operators, datasets, fields, and simulation options."""

from __future__ import annotations

from typing import Any

from .client import BrainAPISession


def get_simulation_options(session: BrainAPISession) -> dict[str, Any]:
    """Fetch raw OPTIONS payload for /simulations."""
    r = session.options("/simulations")
    if r.status_code // 100 != 2:
        raise RuntimeError(f"OPTIONS /simulations failed: {r.status_code} {r.text}")
    return r.json()


def parse_simulation_allowed_values(options_payload: dict[str, Any]) -> dict[str, Any]:
    """Extract commonly used allowed values from nested OPTIONS payload."""
    settings = (
        options_payload.get("actions", {})
        .get("POST", {})
        .get("settings", {})
        .get("children", {})
    )

    extracted: dict[str, Any] = {}
    for key in ("instrumentType", "region", "universe", "neutralization", "delay", "language"):
        node = settings.get(key, {})
        extracted[key] = {
            "label": node.get("label"),
            "choices": node.get("choices"),
            "type": node.get("type"),
        }
    return extracted


def get_operators(session: BrainAPISession) -> list[dict[str, Any]]:
    """Fetch operator metadata."""
    r = session.get("/operators")
    if r.status_code // 100 != 2:
        raise RuntimeError(f"GET /operators failed: {r.status_code} {r.text}")
    payload = r.json()
    if isinstance(payload, list):
        return payload
    return payload.get("results", [])


def _page_results(
    session: BrainAPISession,
    endpoint: str,
    params: dict[str, Any],
    *,
    limit: int = 50,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page = 0

    while True:
        query = dict(params)
        query["limit"] = limit
        query["offset"] = offset

        r = session.get(endpoint, params=query)
        if r.status_code // 100 != 2:
            raise RuntimeError(f"GET {endpoint} failed: {r.status_code} {r.text}")

        payload = r.json()
        results = payload.get("results", [])
        count = payload.get("count", 0)

        if not results:
            break

        rows.extend(results)
        offset += limit
        page += 1

        if offset >= count:
            break
        if max_pages is not None and page >= max_pages:
            break

    return rows


def get_datasets(
    session: BrainAPISession,
    *,
    instrument_type: str,
    region: str,
    delay: int,
    universe: str,
    theme: str | None = None,
    search: str | None = None,
    category: str | None = None,
    limit: int = 50,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch datasets with pagination."""
    params: dict[str, Any] = {
        "instrumentType": instrument_type,
        "region": region,
        "delay": delay,
        "universe": universe,
    }
    if theme is not None:
        params["theme"] = theme
    if search:
        params["search"] = search
    if category:
        params["category"] = category

    return _page_results(session, "/data-sets", params, limit=limit, max_pages=max_pages)


def get_data_fields(
    session: BrainAPISession,
    *,
    instrument_type: str,
    region: str,
    delay: int,
    universe: str,
    dataset_id: str | None = None,
    field_type: str | None = None,
    search: str | None = None,
    limit: int = 50,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch data fields with pagination."""
    params: dict[str, Any] = {
        "instrumentType": instrument_type,
        "region": region,
        "delay": delay,
        "universe": universe,
    }
    if dataset_id:
        params["dataset.id"] = dataset_id
    if field_type:
        params["type"] = field_type
    if search:
        params["search"] = search

    return _page_results(session, "/data-fields", params, limit=limit, max_pages=max_pages)
