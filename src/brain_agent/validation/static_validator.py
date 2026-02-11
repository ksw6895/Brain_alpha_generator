"""Static FastExpr validation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..schemas import ValidationReport


ALLOWED_CHAR_RE = re.compile(r"^[A-Za-z0-9_.,()\-+*/\s]+$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


VALIDATION_ERROR_TAXONOMY: list[dict[str, str]] = [
    {
        "error_key": "empty_expression",
        "match_pattern": r"^Expression is empty$",
        "severity": "high",
        "fix_hint": "식이 비어 있습니다. FastExpr 본문을 생성하고 마지막 반환식을 포함하세요.",
    },
    {
        "error_key": "unsupported_characters",
        "match_pattern": r"Expression contains unsupported characters",
        "severity": "high",
        "fix_hint": "허용되지 않은 문자를 제거하고 FastExpr 연산자/식별자만 사용하세요.",
    },
    {
        "error_key": "unbalanced_parentheses",
        "match_pattern": r"Parentheses are not balanced",
        "severity": "high",
        "fix_hint": "괄호 쌍을 맞추고 중첩 호출을 단순화하세요.",
    },
    {
        "error_key": "unknown_operator",
        "match_pattern": r"Unknown operator:",
        "severity": "high",
        "fix_hint": "retrieval pack 내 candidate_operators 목록에서 연산자로 치환하세요.",
    },
    {
        "error_key": "unknown_data_field",
        "match_pattern": r"Unknown data field:",
        "severity": "high",
        "fix_hint": "retrieval pack 내 candidate_fields 목록에서 필드로 치환하세요.",
    },
    {
        "error_key": "operator_no_arguments",
        "match_pattern": r"Operator .+ has no arguments",
        "severity": "medium",
        "fix_hint": "operator signature에 맞는 필수 인자를 채우세요.",
    },
    {
        "error_key": "operator_empty_argument",
        "match_pattern": r"Operator .+ has an empty argument",
        "severity": "medium",
        "fix_hint": "빈 인자를 제거하고 positional 순서를 다시 맞추세요.",
    },
    {
        "error_key": "operator_arity_mismatch",
        "match_pattern": r"Operator .+ expects .+ args but got .+",
        "severity": "high",
        "fix_hint": "definition의 인자 개수와 순서를 정확히 맞추세요.",
    },
    {
        "error_key": "operator_scope_violation",
        "match_pattern": r"scope .* is not valid in REGULAR",
        "severity": "high",
        "fix_hint": "REGULAR scope를 지원하는 연산자로 교체하세요.",
    },
    {
        "error_key": "ts_non_matrix_input",
        "match_pattern": r"ts_ operator .+ received non-MATRIX field",
        "severity": "high",
        "fix_hint": "ts_ 계열에는 MATRIX 필드만 입력하세요.",
    },
    {
        "error_key": "group_requires_group_and_matrix",
        "match_pattern": r"group_ operator .+ requires GROUP and MATRIX fields",
        "severity": "high",
        "fix_hint": "group_ 연산자는 GROUP 필드와 MATRIX 필드를 함께 넣으세요.",
    },
    {
        "error_key": "vector_used_in_non_vec",
        "match_pattern": r"VECTOR field .+ used in non-vec_ operator",
        "severity": "high",
        "fix_hint": "VECTOR 필드는 vec_ 계열로 먼저 집계한 뒤 사용하세요.",
    },
]


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


def classify_validation_error(error: str) -> dict[str, str]:
    """Map one validator error message to standardized error taxonomy."""
    text = str(error or "")
    for row in VALIDATION_ERROR_TAXONOMY:
        if re.search(row["match_pattern"], text):
            return {
                "error_key": row["error_key"],
                "severity": row["severity"],
                "fix_hint": row["fix_hint"],
                "match_pattern": row["match_pattern"],
            }
    return {
        "error_key": "unknown_validation_error",
        "severity": "medium",
        "fix_hint": "오류 메시지를 확인하고 operator/field/scope/type을 순서대로 점검하세요.",
        "match_pattern": ".*",
    }


def classify_validation_errors(errors: list[str]) -> list[dict[str, str]]:
    """Map a list of validator errors to taxonomy entries without duplication."""
    out: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for message in errors:
        mapped = classify_validation_error(message)
        key = mapped["error_key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({**mapped, "message": message})
    return out
