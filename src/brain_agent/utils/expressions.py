"""Expression text utilities."""

from __future__ import annotations

import re


WHITESPACE_RE = re.compile(r"\s+")


def normalize_expression(expression: str) -> str:
    """Normalize expression for approximate deduping."""
    compact = WHITESPACE_RE.sub(" ", expression).strip()
    compact = compact.replace("( ", "(").replace(" )", ")")
    return compact
