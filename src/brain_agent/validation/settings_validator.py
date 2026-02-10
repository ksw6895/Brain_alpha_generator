"""Simulation settings validator using OPTIONS /simulations payload."""

from __future__ import annotations

from typing import Any


class SimulationSettingsValidator:
    """Validate setting values against allowed values from OPTIONS payload."""

    def __init__(self, options_payload: dict[str, Any]) -> None:
        self.options_payload = options_payload
        self.allowed = self._extract_allowed(options_payload)

    def validate(self, settings: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        for key, allowed_values in self.allowed.items():
            if key not in settings:
                continue
            value = settings[key]
            if allowed_values and str(value) not in allowed_values:
                errors.append(f"Invalid {key}={value}; allowed sample={sorted(list(allowed_values))[:20]}")

        return errors

    def _extract_allowed(self, payload: dict[str, Any]) -> dict[str, set[str]]:
        children = (
            payload.get("actions", {})
            .get("POST", {})
            .get("settings", {})
            .get("children", {})
        )

        out: dict[str, set[str]] = {}
        for key, node in children.items():
            out[key] = _collect_choice_values(node.get("choices"))
        return out


def _collect_choice_values(choices: Any) -> set[str]:
    values: set[str] = set()

    if isinstance(choices, list):
        for row in choices:
            if isinstance(row, dict) and "value" in row:
                values.add(str(row["value"]))
        return values

    if isinstance(choices, dict):
        for child in choices.values():
            values |= _collect_choice_values(child)
        return values

    return values
