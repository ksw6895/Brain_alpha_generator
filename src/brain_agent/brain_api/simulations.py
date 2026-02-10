"""Simulation endpoint helpers."""

from __future__ import annotations

import time
from typing import Any

from .client import BrainAPISession


def _sleep_from_retry_after(headers: dict[str, str], floor_sec: float = 1.0) -> float:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if not retry_after:
        return 0.0
    sleep_sec = max(float(retry_after), floor_sec)
    time.sleep(sleep_sec)
    return sleep_sec


def start_simulation(session: BrainAPISession, payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Start simulation and return progress URL from Location header."""
    r = session.post("/simulations", json=payload)
    if r.status_code // 100 != 2:
        raise RuntimeError(f"POST /simulations failed: {r.status_code} {r.text}")

    location = r.headers.get("Location")
    if not location:
        raise RuntimeError("Simulation response missing Location header")
    return location


def poll_simulation(session: BrainAPISession, location: str, *, max_rounds: int = 1000) -> dict[str, Any]:
    """Poll simulation progress URL until completion."""
    for _ in range(max_rounds):
        r = session.get(location, ensure_login=False)
        if r.status_code // 100 != 2:
            raise RuntimeError(f"GET {location} failed: {r.status_code} {r.text}")

        if _sleep_from_retry_after(r.headers) == 0:
            return r.json()
    raise TimeoutError(f"Simulation polling exceeded max rounds: {location}")


def get_alpha(session: BrainAPISession, alpha_id: str) -> dict[str, Any]:
    """Fetch alpha detail payload."""
    r = session.get(f"/alphas/{alpha_id}")
    if r.status_code // 100 != 2:
        raise RuntimeError(f"GET /alphas/{alpha_id} failed: {r.status_code} {r.text}")
    return r.json()


def get_alpha_recordsets(session: BrainAPISession, alpha_id: str) -> list[str]:
    """List available recordset names for an alpha."""
    r = session.get(f"/alphas/{alpha_id}/recordsets")
    if r.status_code // 100 != 2:
        return []

    payload = r.json()
    if isinstance(payload, list):
        return [str(x) for x in payload]
    if isinstance(payload, dict):
        if "results" in payload and isinstance(payload["results"], list):
            names: list[str] = []
            for row in payload["results"]:
                if isinstance(row, dict) and "name" in row:
                    names.append(str(row["name"]))
                else:
                    names.append(str(row))
            return names
        if "recordsets" in payload and isinstance(payload["recordsets"], list):
            return [str(x) for x in payload["recordsets"]]
    return []


def get_recordset(session: BrainAPISession, alpha_id: str, recordset_name: str) -> dict[str, Any]:
    """Fetch single recordset payload."""
    r = session.get(f"/alphas/{alpha_id}/recordsets/{recordset_name}")
    if r.status_code // 100 != 2:
        raise RuntimeError(
            f"GET /alphas/{alpha_id}/recordsets/{recordset_name} failed: "
            f"{r.status_code} {r.text}"
        )
    return r.json()


def run_single_simulation(session: BrainAPISession, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one simulation to completion and return alpha payload."""
    location = start_simulation(session, payload)
    progress = poll_simulation(session, location)
    alpha_id = progress.get("alpha")
    if not alpha_id:
        raise RuntimeError(f"Simulation completed without alpha id: {progress}")
    return get_alpha(session, str(alpha_id))


def run_multi_simulation(session: BrainAPISession, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run multi-simulation and return all child alpha payloads."""
    location = start_simulation(session, payloads)
    progress = poll_simulation(session, location)

    children = progress.get("children", [])
    if not children:
        alpha_id = progress.get("alpha")
        if alpha_id:
            return [get_alpha(session, str(alpha_id))]
        return []

    out: list[dict[str, Any]] = []
    for child_id in children:
        child = session.get(f"/simulations/{child_id}")
        if child.status_code // 100 != 2:
            continue
        child_payload = child.json()
        alpha_id = child_payload.get("alpha")
        if alpha_id:
            out.append(get_alpha(session, str(alpha_id)))
    return out
