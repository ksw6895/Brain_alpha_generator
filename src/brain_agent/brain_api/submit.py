"""Optional submit endpoint wrappers."""

from __future__ import annotations

from typing import Any

from .client import BrainAPISession


def submit_alpha(session: BrainAPISession, alpha_id: str) -> dict[str, Any]:
    """Submit alpha and return initial response payload."""
    r = session.post(f"/alphas/{alpha_id}/submit")
    if r.status_code not in (200, 201, 202, 204, 403):
        raise RuntimeError(f"submit failed: {r.status_code} {r.text}")
    payload: dict[str, Any]
    try:
        payload = r.json()
    except Exception:
        payload = {"status_code": r.status_code, "text": r.text}
    payload["status_code"] = r.status_code
    return payload


def get_submit_status(session: BrainAPISession, alpha_id: str) -> dict[str, Any]:
    """Poll submit status endpoint."""
    r = session.poll_with_retry_after(f"/alphas/{alpha_id}/submit")
    if r.status_code // 100 != 2:
        raise RuntimeError(f"submit status failed: {r.status_code} {r.text}")
    return r.json()
