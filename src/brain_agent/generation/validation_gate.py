"""Step-21 validation-first gate and deterministic repair helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .prompting import parse_candidate_alpha, parse_with_format_repair
from ..retrieval.pack_builder import RetrievalPack
from ..schemas import CandidateAlpha, ValidationReport
from ..validation.static_validator import VALIDATION_ERROR_TAXONOMY, StaticValidator


UNKNOWN_OPERATOR_RE = re.compile(r"Unknown operator:\s*([A-Za-z_][A-Za-z0-9_]*)")
UNKNOWN_FIELD_RE = re.compile(r"Unknown data field:\s*([A-Za-z_][A-Za-z0-9_]*)")
SCOPE_VIOLATION_RE = re.compile(r"Operator\s+([A-Za-z_][A-Za-z0-9_]*)\s+scope")
TS_NON_MATRIX_RE = re.compile(r"received non-MATRIX field\s+([A-Za-z_][A-Za-z0-9_]*)")
VECTOR_NON_VEC_RE = re.compile(r"VECTOR field\s+([A-Za-z_][A-Za-z0-9_]*)")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
OP_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str
    fix_hint: str


@dataclass
class ValidationGateResult:
    report: ValidationReport
    issues: list[ValidationIssue]
    error_signature: str

    @property
    def is_valid(self) -> bool:
        return bool(self.report.is_valid)


class ValidationGate:
    """Static validator wrapper with taxonomy mapping and repair guidance."""

    def __init__(self, validator: StaticValidator) -> None:
        self.validator = validator
        self._taxonomy: list[tuple[str, re.Pattern[str], str, str]] = []
        for row in VALIDATION_ERROR_TAXONOMY:
            pattern = str(row.get("match_pattern") or "")
            if not pattern:
                continue
            self._taxonomy.append(
                (
                    str(row.get("error_key") or "validation_error"),
                    re.compile(pattern),
                    str(row.get("severity") or "medium"),
                    str(row.get("fix_hint") or ""),
                )
            )

    def validate_candidate(self, candidate: CandidateAlpha) -> ValidationGateResult:
        expression = _candidate_expression(candidate)
        report = self.validator.validate(expression, alpha_type=candidate.simulation_settings.type)
        issues = self.classify_errors(report.errors)
        signature = "|".join(sorted(issue.code for issue in issues)) if issues else "VALID"
        return ValidationGateResult(report=report, issues=issues, error_signature=signature)

    def classify_errors(self, errors: list[str]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for message in errors:
            mapped = self._map_error(message)
            issues.append(mapped)
        return issues

    def build_repair_instruction(
        self,
        *,
        candidate: CandidateAlpha,
        issues: list[ValidationIssue],
        retrieval_pack: RetrievalPack,
        attempt: int,
        repeated_error_count: int,
        expanded_retrieval: bool,
    ) -> dict[str, Any]:
        error_codes = [issue.code for issue in issues]
        rulebook = _repair_rulebook(error_codes)
        return {
            "attempt": int(attempt),
            "error_codes": error_codes,
            "errors": [issue.message for issue in issues],
            "repeated_error_count": int(repeated_error_count),
            "expanded_retrieval": bool(expanded_retrieval),
            "candidate_lane": candidate.generation_notes.candidate_lane,
            "rulebook": rulebook,
            "available_candidates": {
                "fields": len(retrieval_pack.candidate_fields),
                "operators": len(retrieval_pack.candidate_operators),
                "subcategories": len(retrieval_pack.selected_subcategories),
            },
        }

    def repair_candidate(
        self,
        *,
        candidate: CandidateAlpha,
        issues: list[ValidationIssue],
        retrieval_pack: RetrievalPack,
    ) -> CandidateAlpha:
        repaired = candidate.model_copy(deep=True)
        expression = _candidate_expression(repaired)
        codes = {issue.code for issue in issues}
        errors = [issue.message for issue in issues]

        if not expression.strip() or "empty_expression" in codes:
            expression = self._synthesize_expression(retrieval_pack)

        if "unsupported_characters" in codes:
            expression = re.sub(r"[^A-Za-z0-9_.,()\-+*/\s]", "", expression)

        unknown_operators = _extract_all(UNKNOWN_OPERATOR_RE, errors)
        if unknown_operators:
            replacement = self._pick_regular_operator(retrieval_pack, exclude=set(unknown_operators))
            if replacement:
                for unknown in unknown_operators:
                    expression = re.sub(rf"\b{re.escape(unknown)}(?=\s*\()", replacement, expression)

        scope_ops = _extract_all(SCOPE_VIOLATION_RE, errors)
        if scope_ops:
            replacement = self._pick_regular_operator(retrieval_pack, exclude=set(scope_ops))
            if replacement:
                for op in scope_ops:
                    expression = re.sub(rf"\b{re.escape(op)}(?=\s*\()", replacement, expression)

        unknown_fields = _extract_all(UNKNOWN_FIELD_RE, errors)
        if unknown_fields:
            replacement = self._pick_field_id(retrieval_pack, preferred_type="MATRIX")
            if replacement:
                for field_id in unknown_fields:
                    expression = _replace_identifier(expression, field_id, replacement)

        ts_bad_fields = _extract_all(TS_NON_MATRIX_RE, errors)
        if ts_bad_fields:
            matrix_field = self._pick_field_id(retrieval_pack, preferred_type="MATRIX")
            if matrix_field:
                for field_id in ts_bad_fields:
                    expression = _replace_identifier(expression, field_id, matrix_field)

        vector_bad_fields = _extract_all(VECTOR_NON_VEC_RE, errors)
        if vector_bad_fields:
            matrix_field = self._pick_field_id(retrieval_pack, preferred_type="MATRIX")
            if matrix_field:
                for field_id in vector_bad_fields:
                    expression = _replace_identifier(expression, field_id, matrix_field)

        structural_codes = {
            "operator_no_arguments",
            "operator_empty_argument",
            "operator_arity_mismatch",
            "unbalanced_parentheses",
        }
        if "group_requires_group_and_matrix" in codes:
            expression = self._build_group_expression(retrieval_pack) or self._synthesize_expression(retrieval_pack)
        elif codes.intersection(structural_codes):
            expression = self._synthesize_expression(retrieval_pack)

        repaired.simulation_settings.regular = expression.strip()
        repaired.generation_notes.used_fields = _infer_used_fields(expression)
        repaired.generation_notes.used_operators = _infer_used_operators(expression)

        # Last-resort fallback if heuristic edits are still invalid.
        post = self.validator.validate(repaired.simulation_settings.regular or "", alpha_type="REGULAR")
        if not post.is_valid:
            repaired.simulation_settings.regular = self._synthesize_expression(retrieval_pack)
            repaired.generation_notes.used_fields = _infer_used_fields(repaired.simulation_settings.regular or "")
            repaired.generation_notes.used_operators = _infer_used_operators(repaired.simulation_settings.regular or "")
        return repaired

    def parse_candidate_with_format_repair(self, raw_text: str) -> tuple[CandidateAlpha, bool]:
        return parse_with_format_repair(raw_text, parser=parse_candidate_alpha)

    def _map_error(self, message: str) -> ValidationIssue:
        text = str(message or "")
        for error_key, pattern, severity, fix_hint in self._taxonomy:
            if pattern.search(text):
                return ValidationIssue(
                    code=error_key,
                    message=text,
                    severity=severity,
                    fix_hint=fix_hint,
                )
        return ValidationIssue(
            code="validation_error",
            message=text,
            severity="medium",
            fix_hint="오류 메시지를 기준으로 식/인자를 재구성하세요.",
        )

    def _synthesize_expression(self, retrieval_pack: RetrievalPack) -> str:
        matrix_field = self._pick_field_id(retrieval_pack, preferred_type="MATRIX")
        group_field = self._pick_field_id(retrieval_pack, preferred_type="GROUP")
        any_field = matrix_field or self._pick_field_id(retrieval_pack) or "close"
        operators = {str(item.name) for item in retrieval_pack.candidate_operators if item.name}

        templates: list[tuple[str, set[str]]] = [
            (f"rank(ts_delta({any_field}, 5))", {"rank", "ts_delta"}),
            (f"zscore(ts_delta({any_field}, 5))", {"zscore", "ts_delta"}),
            (f"ts_delta({any_field}, 5)", {"ts_delta"}),
            (f"rank({any_field})", {"rank"}),
            (f"zscore({any_field})", {"zscore"}),
        ]

        if matrix_field and group_field:
            templates.insert(0, (f"group_rank({matrix_field}, {group_field})", {"group_rank"}))

        for expr, required_ops in templates:
            if required_ops and not required_ops.issubset(operators):
                continue
            if self.validator.validate(expr, alpha_type="REGULAR").is_valid:
                return expr

        # Fall back to known operator universe from validator rows.
        for expr, _ in templates:
            if self.validator.validate(expr, alpha_type="REGULAR").is_valid:
                return expr

        # Final deterministic fallback.
        if self.validator.validate(any_field, alpha_type="REGULAR").is_valid:
            return any_field

        fallback_field = self._fallback_field_from_validator(preferred_type="MATRIX")
        if fallback_field:
            if self.validator.validate(f"rank({fallback_field})", alpha_type="REGULAR").is_valid:
                return f"rank({fallback_field})"
            if self.validator.validate(fallback_field, alpha_type="REGULAR").is_valid:
                return fallback_field
        return any_field

    def _build_group_expression(self, retrieval_pack: RetrievalPack) -> str | None:
        matrix_field = self._pick_field_id(retrieval_pack, preferred_type="MATRIX")
        group_field = self._pick_field_id(retrieval_pack, preferred_type="GROUP")
        if not matrix_field or not group_field:
            return None
        candidates = [
            "group_rank",
            "group_zscore",
            "group_mean",
            "group_neutralize",
        ]
        available = {str(item.name) for item in retrieval_pack.candidate_operators if item.name}
        for op in candidates:
            if op not in available:
                continue
            expr = f"{op}({matrix_field}, {group_field})"
            if self.validator.validate(expr, alpha_type="REGULAR").is_valid:
                return expr
        return None

    def _pick_regular_operator(self, retrieval_pack: RetrievalPack, *, exclude: set[str] | None = None) -> str | None:
        exclude_set = {str(item) for item in (exclude or set())}
        preferred = ["rank", "zscore", "ts_delta", "ts_mean", "ts_stddev"]
        candidates: list[str] = []
        for op in retrieval_pack.candidate_operators:
            name = str(op.name or "")
            if not name or name in exclude_set:
                continue
            scopes = {str(scope).upper() for scope in op.scope}
            if scopes and "REGULAR" not in scopes:
                continue
            candidates.append(name)

        for name in preferred:
            if name in candidates:
                return name
        if candidates:
            return candidates[0]

        for name in preferred:
            if name in self.validator.operators:
                scope = {str(x).upper() for x in self.validator.operator_scopes.get(name, set())}
                if not scope or "REGULAR" in scope:
                    return name

        for name, scopes in self.validator.operator_scopes.items():
            if name in exclude_set:
                continue
            upper = {str(x).upper() for x in scopes}
            if not upper or "REGULAR" in upper:
                return name
        return None

    def _pick_field_id(self, retrieval_pack: RetrievalPack, *, preferred_type: str | None = None) -> str | None:
        if preferred_type:
            for field in retrieval_pack.candidate_fields:
                if str(field.type or "").upper() == preferred_type.upper():
                    return str(field.id)
        for field in retrieval_pack.candidate_fields:
            return str(field.id)
        return self._fallback_field_from_validator(preferred_type=preferred_type)

    def _fallback_field_from_validator(self, *, preferred_type: str | None = None) -> str | None:
        if preferred_type:
            for field_id, field_type in self.validator.field_types.items():
                if str(field_type).upper() == preferred_type.upper():
                    return field_id
        for field_id in self.validator.fields.keys():
            return field_id
        return None


def _extract_all(pattern: re.Pattern[str], messages: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for message in messages:
        for matched in pattern.findall(str(message or "")):
            value = str(matched).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
    return out


def _replace_identifier(expression: str, source: str, target: str) -> str:
    if not source or not target or source == target:
        return expression
    return re.sub(rf"\b{re.escape(source)}\b", target, expression)


def _infer_used_operators(expression: str) -> list[str]:
    return _unique([match.group(1) for match in OP_CALL_RE.finditer(expression or "")])


def _infer_used_fields(expression: str) -> list[str]:
    operators = set(_infer_used_operators(expression))
    blacklist = operators | {"if", "else", "and", "or", "not", "true", "false", "null"}
    return _unique([item for item in IDENT_RE.findall(expression or "") if item not in blacklist])


def _candidate_expression(candidate: CandidateAlpha) -> str:
    sim = candidate.simulation_settings
    return sim.regular or sim.combo or ""


def _repair_rulebook(error_codes: list[str]) -> list[str]:
    rules: list[str] = []
    code_set = set(error_codes)

    if {"unknown_operator", "unknown_data_field"}.intersection(code_set):
        rules.append("retrieval pack 후보(operator/field)로 우선 치환")
    if "operator_scope_violation" in code_set:
        rules.append("REGULAR scope 허용 연산자로 교체")
    if {
        "ts_non_matrix_input",
        "group_requires_group_and_matrix",
        "vector_used_in_non_vec",
    }.intersection(code_set):
        rules.append("ts_/group_/vec_ 타입 규칙에 맞게 필드 조합 재배치")
    if {
        "operator_no_arguments",
        "operator_empty_argument",
        "operator_arity_mismatch",
        "unbalanced_parentheses",
    }.intersection(code_set):
        rules.append("구조(괄호/인자)를 다시 생성하는 포맷 복구 우선")
    if not rules:
        rules.append("오류 메시지의 핵심 토큰을 기준으로 식을 단순화")
    return rules


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def dump_instruction_json(payload: dict[str, Any]) -> str:
    """Stable helper for logging deterministic repair instructions."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
