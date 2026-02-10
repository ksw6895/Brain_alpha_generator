"""Metadata endpoints for operators, datasets, fields, and simulation options."""

from __future__ import annotations

import math
import random
import sys
import time
from collections.abc import Callable
from typing import Any

from .client import BrainAPISession

_RATE_LIMIT_COOLDOWN_UNTIL: dict[str, float] = {}
_RATE_LIMIT_STREAK: dict[str, int] = {}
_RATE_LIMIT_LAST_429_AT: dict[str, float] = {}


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
    max_retries: int = 8,
    wait_on_rate_limit: bool = True,
    max_total_wait_sec: int = 60 * 60 * 24,
    on_page: Callable[[list[dict[str, Any]], int, int], None] | None = None,
    collect_results: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page = 0

    while True:
        query = dict(params)
        query["limit"] = limit
        query["offset"] = offset

        r = _get_with_backoff(
            session,
            endpoint,
            query,
            max_retries=max_retries,
            wait_on_rate_limit=wait_on_rate_limit,
            max_total_wait_sec=max_total_wait_sec,
        )
        if r.status_code // 100 != 2:
            if r.status_code == 429:
                remaining = r.headers.get("X-Ratelimit-Remaining") or r.headers.get("x-ratelimit-remaining")
                reset = r.headers.get("X-Ratelimit-Reset") or r.headers.get("x-ratelimit-reset")
                raise RuntimeError(
                    f"GET {endpoint} failed: 429 API rate limit exceeded. "
                    f"remaining={remaining}, reset={reset}. "
                    "Retry later or use --wait-on-rate-limit."
                )
            raise RuntimeError(f"GET {endpoint} failed: {r.status_code} {r.text}")

        payload = r.json()
        results = payload.get("results", [])
        count = payload.get("count", 0)

        if not results:
            break

        if on_page is not None:
            on_page(results, offset, count)

        if collect_results:
            rows.extend(results)
        offset += limit
        page += 1

        if offset >= count:
            break
        if max_pages is not None and page >= max_pages:
            break

    return rows


def _get_with_backoff(
    session: BrainAPISession,
    endpoint: str,
    params: dict[str, Any],
    *,
    max_retries: int,
    wait_on_rate_limit: bool,
    max_total_wait_sec: int,
) -> Any:
    """GET with Retry-After aware backoff for 429/5xx responses."""
    attempt = 0
    total_wait = 0.0
    while True:
        cooldown_until = _RATE_LIMIT_COOLDOWN_UNTIL.get(endpoint, 0.0)
        now = time.time()
        if wait_on_rate_limit and cooldown_until > now:
            pre_wait = cooldown_until - now
            streak = max(_RATE_LIMIT_STREAK.get(endpoint, 0), 1)
            _log_wait(endpoint, 429, pre_wait, streak, total_wait + pre_wait, source="cooldown")
            time.sleep(pre_wait)
            total_wait += pre_wait

        r = session.get(endpoint, params=params)
        if r.status_code // 100 == 2:
            now = time.time()
            last_429_at = _RATE_LIMIT_LAST_429_AT.get(endpoint, 0.0)
            if now - last_429_at > 120.0:
                _RATE_LIMIT_STREAK[endpoint] = 0
            else:
                # Keep some pressure when 429s are intermittent but frequent.
                prev = _RATE_LIMIT_STREAK.get(endpoint, 0)
                _RATE_LIMIT_STREAK[endpoint] = max(prev - 1, 1) if prev > 0 else 0
            _RATE_LIMIT_COOLDOWN_UNTIL.pop(endpoint, None)
            return r

        if r.status_code not in (429, 500, 502, 503, 504):
            return r

        # Explicit fail-fast mode for 429 throttling.
        if r.status_code == 429 and not wait_on_rate_limit:
            return r

        if r.status_code == 429 and wait_on_rate_limit:
            _RATE_LIMIT_LAST_429_AT[endpoint] = time.time()
            streak = _RATE_LIMIT_STREAK.get(endpoint, 0) + 1
            _RATE_LIMIT_STREAK[endpoint] = streak
            sleep_sec = _sleep_seconds_from_headers(r, attempt, streak)
            _RATE_LIMIT_COOLDOWN_UNTIL[endpoint] = time.time() + sleep_sec
            total_wait += sleep_sec
            if total_wait > max_total_wait_sec:
                return r
            _log_wait(endpoint, r.status_code, sleep_sec, streak, total_wait, source="429")
            time.sleep(sleep_sec)
            attempt += 1
            continue

        if attempt >= max_retries:
            return r

        sleep_sec = _sleep_seconds_from_headers(r, attempt, streak=0)
        total_wait += sleep_sec
        if total_wait > max_total_wait_sec:
            return r
        _log_wait(endpoint, r.status_code, sleep_sec, attempt + 1, total_wait, source="retry")
        time.sleep(sleep_sec)
        attempt += 1


def _sleep_seconds_from_headers(response: Any, attempt: int, streak: int) -> float:
    retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
    rate_limit_reset = response.headers.get("X-Ratelimit-Reset") or response.headers.get("x-ratelimit-reset")
    server_wait: float | None = None
    if retry_after:
        try:
            server_wait = max(float(retry_after), 1.0)
        except ValueError:
            server_wait = None
    elif rate_limit_reset:
        try:
            # X-Ratelimit-Reset is typically seconds until reset.
            server_wait = max(float(rate_limit_reset), 2.0)
        except ValueError:
            server_wait = None

    # For 429, enforce exponential growth by streak even if server hints are tiny.
    # This avoids pathological fixed 2-second loops.
    if response.status_code == 429:
        backoff_wait = _exp_backoff(streak if streak > 0 else attempt + 1)
        sleep_sec = max(server_wait or 0.0, backoff_wait)
    else:
        sleep_sec = server_wait if server_wait is not None else _exp_backoff(attempt + 1)

    # Jitter avoids synchronized retries across processes.
    return min(sleep_sec + random.uniform(0.0, 1.0), 60 * 60 * 6)


def _exp_backoff(step: int) -> float:
    # step=1 => ~2s, step=2 => ~4s, step=3 => ~8s ...
    step = max(step, 1)
    return min(2.0 * (2 ** min(step - 1, 12)), 60 * 30)


def _log_wait(
    endpoint: str,
    status_code: int,
    sleep_sec: float,
    attempt: int,
    total_wait: float,
    *,
    source: str,
) -> None:
    msg = (
        f"[RATE-LIMIT] {endpoint} returned {status_code}. "
        f"waiting {math.ceil(sleep_sec)}s (attempt={attempt}, total_wait={math.ceil(total_wait)}s, source={source})"
    )
    print(msg, file=sys.stderr, flush=True)


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
    wait_on_rate_limit: bool = True,
    on_page: Callable[[list[dict[str, Any]], int, int], None] | None = None,
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

    return _page_results(
        session,
        "/data-sets",
        params,
        limit=limit,
        max_pages=max_pages,
        wait_on_rate_limit=wait_on_rate_limit,
        on_page=on_page,
    )


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
    wait_on_rate_limit: bool = True,
    on_page: Callable[[list[dict[str, Any]], int, int], None] | None = None,
    collect_results: bool = True,
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

    return _page_results(
        session,
        "/data-fields",
        params,
        limit=limit,
        max_pages=max_pages,
        wait_on_rate_limit=wait_on_rate_limit,
        on_page=on_page,
        collect_results=collect_results,
    )
