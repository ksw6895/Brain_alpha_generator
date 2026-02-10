"""Static FastExpr validation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..schemas import ValidationReport


ALLOWED_CHAR_RE = re.compile(r"^[A-Za-z0-9_.,()\-+*/\s]+$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


@dataclass
class FunctionCall:
    name: str
    args: list[str]


class StaticValidator:
    """Minimal static validator to reduce simulation failures."""

    def __init__(
        self,
        *,
        operators: list[dict[str, Any]],
        fields: list[dict[str, Any]],
        safe_regular_only: bool = True,
    ) -> None:
        self.operators = {str(row.get("name")): row for row in operators if row.get("name")}
        self.fields = {str(row.get("id")): row for row in fields if row.get("id")}
        self.safe_regular_only = safe_regular_only

        self.operator_scopes = {name: _parse_scope(row.get("scope")) for name, row in self.operators.items()}
        self.operator_arity = {name: _extract_arity(row) for name, row in self.operators.items()}
        self.field_types = {field_id: str(row.get("type", "")).upper() for field_id, row in self.fields.items()}

    def validate(self, expression: str, *, alpha_type: str = "REGULAR") -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []

        if not expression.strip():
            return ValidationReport(is_valid=False, errors=["Expression is empty"])

        if not ALLOWED_CHAR_RE.match(expression):
            errors.append("Expression contains unsupported characters")

        if not _balanced_parentheses(expression):
            errors.append("Parentheses are not balanced")

        calls = _extract_calls(expression)
        used_operators = _unique([call.name for call in calls])

        # Function/operator checks
        for call in calls:
            if call.name not in self.operators:
                errors.append(f"Unknown operator: {call.name}")
                continue

            if not call.args:
                errors.append(f"Operator {call.name} has no arguments")

            if any(not arg.strip() for arg in call.args):
                errors.append(f"Operator {call.name} has an empty argument")

            expected_arity = self.operator_arity.get(call.name)
            if expected_arity is not None and len(call.args) != expected_arity:
                errors.append(
                    f"Operator {call.name} expects {expected_arity} args but got {len(call.args)}"
                )

            scopes = self.operator_scopes.get(call.name, set())
            if scopes:
                upper_scopes = {s.upper() for s in scopes}
                if alpha_type.upper() == "REGULAR" and "REGULAR" not in upper_scopes:
                    errors.append(f"Operator {call.name} scope {sorted(upper_scopes)} is not valid in REGULAR")
            else:
                if self.safe_regular_only and alpha_type.upper() != "REGULAR":
                    errors.append(f"Operator {call.name} has unknown scope and is blocked in non-REGULAR mode")

        # Field existence checks.
        all_identifiers = _unique(IDENT_RE.findall(expression))
        operator_set = set(used_operators)
        used_fields = [tok for tok in all_identifiers if tok not in operator_set and not NUMBER_RE.match(tok)]

        for field_id in used_fields:
            if field_id not in self.fields:
                errors.append(f"Unknown data field: {field_id}")

        # Type heuristics.
        errors.extend(self._type_checks(calls))

        # Optional warning for large expression complexity.
        if len(calls) > 20:
            warnings.append("Expression is complex (>20 calls); consider simplification for stability")

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=_unique(errors),
            warnings=_unique(warnings),
            used_operators=used_operators,
            used_fields=_unique([field for field in used_fields if field in self.fields]),
        )

    def _type_checks(self, calls: list[FunctionCall]) -> list[str]:
        errors: list[str] = []

        for call in calls:
            arg_ids = [tok for tok in _extract_identifiers_from_args(call.args) if tok in self.field_types]
            arg_types = [self.field_types[arg_id] for arg_id in arg_ids]

            if call.name.startswith("ts_"):
                for field_id, field_type in zip(arg_ids, arg_types):
                    if field_type and field_type != "MATRIX":
                        errors.append(
                            f"ts_ operator {call.name} received non-MATRIX field {field_id}:{field_type}"
                        )

            if call.name.startswith("group_"):
                has_group = any(t == "GROUP" for t in arg_types)
                has_matrix = any(t == "MATRIX" for t in arg_types)
                if not (has_group and has_matrix):
                    errors.append(
                        f"group_ operator {call.name} requires GROUP and MATRIX fields"
                    )

            if arg_ids and not call.name.startswith("vec_"):
                vector_fields = [f for f, t in zip(arg_ids, arg_types) if t == "VECTOR"]
                for field_id in vector_fields:
                    errors.append(
                        f"VECTOR field {field_id} used in non-vec_ operator {call.name}"
                    )

        return errors


def _parse_scope(scope_value: Any) -> set[str]:
    if scope_value is None:
        return set()
    if isinstance(scope_value, list):
        return {str(x).upper() for x in scope_value}
    if isinstance(scope_value, str):
        chunks = [x.strip() for x in scope_value.split(",") if x.strip()]
        return {x.upper() for x in chunks}
    return set()


def _extract_arity(operator_row: dict[str, Any]) -> int | None:
    for key in ("arity", "nArgs", "numArgs", "argumentCount"):
        value = operator_row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _balanced_parentheses(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _extract_calls(text: str) -> list[FunctionCall]:
    calls: list[FunctionCall] = []
    idx = 0

    while idx < len(text):
        match = IDENT_RE.match(text, idx)
        if not match:
            idx += 1
            continue

        name = match.group(0)
        next_idx = _skip_spaces(text, match.end())
        if next_idx >= len(text) or text[next_idx] != "(":
            idx = match.end()
            continue

        end_idx = _find_closing_paren(text, next_idx)
        if end_idx == -1:
            idx = next_idx + 1
            continue

        arg_text = text[next_idx + 1 : end_idx]
        args = _split_args(arg_text)
        calls.append(FunctionCall(name=name, args=args))

        # Recursively parse nested calls.
        for arg in args:
            calls.extend(_extract_calls(arg))

        idx = end_idx + 1

    return calls


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    depth = 0
    start = 0

    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1

    final = text[start:].strip()
    if final or text.strip() == "":
        args.append(final)

    if len(args) == 1 and args[0] == "":
        return []
    return args


def _find_closing_paren(text: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _skip_spaces(text: str, idx: int) -> int:
    while idx < len(text) and text[idx].isspace():
        idx += 1
    return idx


def _extract_identifiers_from_args(args: list[str]) -> list[str]:
    out: list[str] = []
    for arg in args:
        out.extend(IDENT_RE.findall(arg))
    return out


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
