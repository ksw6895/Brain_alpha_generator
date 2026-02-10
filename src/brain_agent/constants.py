"""Project-wide constants."""

from __future__ import annotations

from pathlib import Path

API_BASE = "https://api.worldquantbrain.com"
DEFAULT_CREDENTIALS_PATH = Path("~/.brain_credentials").expanduser()
DEFAULT_DB_PATH = Path("data/brain_agent.db")
DEFAULT_META_DIR = Path("data/meta")
DEFAULT_EVENTS_PATH = Path("data/events.jsonl")

RECORDSET_NAMES = (
    "pnl",
    "daily-pnl",
    "turnover",
    "yearly-stats",
)
