"""Build FastExpr knowledge packs for LLM generation and frontend visualization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..constants import DEFAULT_META_DIR
from ..storage.sqlite_store import MetadataStore
from ..utils.filesystem import utc_now_iso, write_json
from ..validation.static_validator import (
    VALIDATION_ERROR_TAXONOMY,
    StaticValidator,
    classify_validation_error,
)


class OperatorSignatureEntry(BaseModel):
    name: str
    definition: str | None = None
    scope: list[str] = Field(default_factory=list)
    category: str | None = None
    description: str | None = None


class OperatorSignaturePack(BaseModel):
    version: str = "v1"
    generated_at: str
    operator_count: int
    operators: list[OperatorSignatureEntry] = Field(default_factory=list)
    missing_required_fields: list[dict[str, Any]] = Field(default_factory=list)


class SimulationSettingsAllowedPack(BaseModel):
    version: str = "v1"
    generated_at: str
    snapshot_date: str | None = None
    source: str
    allowed: dict[str, list[Any]] = Field(default_factory=dict)


class FastExprExampleEntry(BaseModel):
    expression: str
    tags: list[str] = Field(default_factory=list)
    used_fields: list[str] = Field(default_factory=list)
    used_operators: list[str] = Field(default_factory=list)
    subcategory_tags: list[str] = Field(default_factory=list)
    source: str
    validation_passed: Literal[True] = True


class FastExprExamplesPack(BaseModel):
    version: str = "v1"
    generated_at: str
    fallback_used: bool = False
    examples: list[FastExprExampleEntry] = Field(default_factory=list)


class CounterExampleCase(BaseModel):
    expression: str
    error_type: str
    error_message: str
    fix_hint: str


class FastExprCounterExamplesPack(BaseModel):
    version: str = "v1"
    generated_at: str
    cases: list[CounterExampleCase] = Field(default_factory=list)


class VisualOperatorCard(BaseModel):
    name: str
    category: str
    scope: list[str] = Field(default_factory=list)
    signature: str
    display: dict[str, str]
    tips: list[str] = Field(default_factory=list)


class VisualExampleCard(BaseModel):
    expression: str
    tags: list[str] = Field(default_factory=list)
    quality_flags: dict[str, bool]


class FastExprVisualPack(BaseModel):
    version: str = "v1"
    generated_at: str
    operators: list[VisualOperatorCard] = Field(default_factory=list)
    error_taxonomy: list[dict[str, str]] = Field(default_factory=list)
    example_cards: list[VisualExampleCard] = Field(default_factory=list)


class KnowledgePackBuildResult(BaseModel):
    output_dir: str
    generated_files: dict[str, str] = Field(default_factory=dict)
    failed_parts: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    fallback_used: bool = False

    @property
    def success(self) -> bool:
        return len(self.failed_parts) == 0


def build_knowledge_packs(
    *,
    store: MetadataStore,
    output_dir: str | Path,
    meta_dir: str | Path = DEFAULT_META_DIR,
) -> KnowledgePackBuildResult:
    """Build and persist step-18 knowledge packs."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_root = Path(meta_dir)

    result = KnowledgePackBuildResult(output_dir=str(out_dir))

    operators = store.list_operators()
    fields = store.list_data_fields()
    datasets = store.list_datasets()
    validator = StaticValidator(operators=operators, fields=fields)

    field_subcategory_lookup = _build_field_subcategory_lookup(fields=fields, datasets=datasets)

    # 1) Operator signature pack
    try:
        operator_pack = _build_operator_signature_pack(operators)
        path = out_dir / "operator_signature_pack.json"
        write_json(path, operator_pack.model_dump(mode="python"))
        result.generated_files["operator_signature_pack"] = str(path)
        result.counts["operators"] = operator_pack.operator_count
    except Exception as exc:
        result.failed_parts["operator_signature_pack"] = str(exc)

    # 2) Settings allowed pack
    try:
        settings_pack = _build_settings_allowed_pack(meta_root)
        path = out_dir / "simulation_settings_allowed_pack.json"
        write_json(path, settings_pack.model_dump(mode="python"))
        result.generated_files["simulation_settings_allowed_pack"] = str(path)
        result.counts["settings_keys"] = len(settings_pack.allowed.keys())
    except Exception as exc:
        result.failed_parts["simulation_settings_allowed_pack"] = str(exc)

    # 3) Examples pack
    try:
        examples_pack = _build_examples_pack(
            validator=validator,
            field_subcategory_lookup=field_subcategory_lookup,
        )
        path = out_dir / "fastexpr_examples_pack.json"
        write_json(path, examples_pack.model_dump(mode="python"))
        result.generated_files["fastexpr_examples_pack"] = str(path)
        result.counts["examples"] = len(examples_pack.examples)
        result.fallback_used = examples_pack.fallback_used
    except Exception as exc:
        result.failed_parts["fastexpr_examples_pack"] = str(exc)
        examples_pack = None

    # 4) Counter-examples pack
    try:
        counterexamples_pack = _build_counterexamples_pack(
            validator=validator,
            fields=fields,
            operators=operators,
        )
        path = out_dir / "fastexpr_counterexamples_pack.json"
        write_json(path, counterexamples_pack.model_dump(mode="python"))
        result.generated_files["fastexpr_counterexamples_pack"] = str(path)
        result.counts["counterexamples"] = len(counterexamples_pack.cases)
    except Exception as exc:
        result.failed_parts["fastexpr_counterexamples_pack"] = str(exc)

    # 5) Visual knowledge pack
    try:
        source_operators = operator_pack.operators if "operator_signature_pack" in result.generated_files else []
        source_examples = examples_pack.examples if examples_pack is not None else []
        visual_pack = _build_visual_pack(
            operators=source_operators,
            examples=source_examples,
        )
        path = out_dir / "fastexpr_visual_pack.json"
        write_json(path, visual_pack.model_dump(mode="python"))
        result.generated_files["fastexpr_visual_pack"] = str(path)
        result.counts["visual_operators"] = len(visual_pack.operators)
    except Exception as exc:
        result.failed_parts["fastexpr_visual_pack"] = str(exc)

    return result


def _build_operator_signature_pack(operators: list[dict[str, Any]]) -> OperatorSignaturePack:
    rows = sorted(
        [row for row in operators if row.get("name")],
        key=lambda row: str(row.get("name")),
    )
    entries: list[OperatorSignatureEntry] = []
    missing: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name"))
        entry = OperatorSignatureEntry(
            name=name,
            definition=_as_optional_text(row.get("definition")),
            scope=_parse_scope(row.get("scope")),
            category=_as_optional_text(row.get("category")),
            description=_as_optional_text(row.get("description")),
        )
        if not entry.definition or not entry.scope:
            missing.append(
                {
                    "name": name,
                    "missing_definition": not bool(entry.definition),
                    "missing_scope": len(entry.scope) == 0,
                }
            )
        entries.append(entry)

    return OperatorSignaturePack(
        generated_at=utc_now_iso(),
        operator_count=len(entries),
        operators=entries,
        missing_required_fields=missing,
    )


def _build_settings_allowed_pack(meta_dir: Path) -> SimulationSettingsAllowedPack:
    primary_path = meta_dir / "simulations_options.json"
    fallback_path = Path("docs/artifacts/fixtures/simulations_options.sample.json")
    source_path = primary_path if primary_path.exists() else fallback_path
    if not source_path.exists():
        raise RuntimeError(f"simulations options not found: {primary_path} or {fallback_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    snapshot_date = payload.get("date")

    if "allowed" in payload and isinstance(payload["allowed"], dict):
        allowed_nodes = payload["allowed"]
    else:
        allowed_nodes = _extract_allowed_nodes_from_raw_options(payload)

    flat_allowed: dict[str, list[Any]] = {}
    for key, node in allowed_nodes.items():
        if not isinstance(node, dict):
            continue
        values = _extract_choice_values(node.get("choices"))
        flat_allowed[key] = values

    return SimulationSettingsAllowedPack(
        generated_at=utc_now_iso(),
        snapshot_date=str(snapshot_date) if snapshot_date else None,
        source=str(source_path),
        allowed=flat_allowed,
    )


def _build_examples_pack(
    *,
    validator: StaticValidator,
    field_subcategory_lookup: dict[str, str],
) -> FastExprExamplesPack:
    candidates = _example_candidates()
    seen_expr: set[str] = set()
    examples: list[FastExprExampleEntry] = []

    for candidate in candidates:
        expression = candidate["expression"].strip()
        if not expression or expression in seen_expr:
            continue
        seen_expr.add(expression)
        report = validator.validate(expression, alpha_type="REGULAR")
        if not report.is_valid:
            continue

        tags = _merge_unique(
            candidate.get("tags", []),
            _rule_tags_for_expression(expression),
        )
        subcategory_tags = _merge_unique(
            [field_subcategory_lookup.get(field, "unknown") for field in report.used_fields],
            [],
        )
        examples.append(
            FastExprExampleEntry(
                expression=expression,
                tags=tags,
                used_fields=report.used_fields,
                used_operators=report.used_operators,
                subcategory_tags=[x for x in subcategory_tags if x and x != "unknown"],
                source=str(candidate.get("source") or "curated"),
            )
        )

    fallback_used = False
    if not examples:
        for fallback_expr in ("rank(ts_delta(log(close), 5))", "ts_step(1)"):
            report = validator.validate(fallback_expr, alpha_type="REGULAR")
            if not report.is_valid:
                continue
            fallback_used = True
            examples.append(
                FastExprExampleEntry(
                    expression=fallback_expr,
                    tags=["starter", "rulebook-aligned", "fallback"],
                    used_fields=report.used_fields,
                    used_operators=report.used_operators,
                    subcategory_tags=[field_subcategory_lookup.get(field, "unknown") for field in report.used_fields],
                    source="fallback",
                )
            )
            break
        if not examples:
            raise RuntimeError("No valid FastExpr examples available and fallback examples failed validation")

    return FastExprExamplesPack(
        generated_at=utc_now_iso(),
        fallback_used=fallback_used,
        examples=examples,
    )


def _build_counterexamples_pack(
    *,
    validator: StaticValidator,
    fields: list[dict[str, Any]],
    operators: list[dict[str, Any]],
) -> FastExprCounterExamplesPack:
    known_operator_names = {str(row.get("name")) for row in operators if row.get("name")}
    known_field_names = {str(row.get("id")) for row in fields if row.get("id")}

    invalid_cases = [
        "unknown_operator(close)",
        "rank(unknown_data_field_123)",
        "rank(absolute_price_change_today)",
        "ts_delta(sector, 5)",
        "group_neutralize(rank(close), returns)",
        "rank(close",
        "",
    ]

    cases: list[CounterExampleCase] = []
    for expression in invalid_cases:
        report = validator.validate(expression, alpha_type="REGULAR")
        if report.is_valid or not report.errors:
            continue
        first = classify_validation_error(report.errors[0])
        # Safety checks to keep counterexamples meaningful.
        if expression and expression in known_operator_names:
            continue
        if expression and expression in known_field_names:
            continue
        cases.append(
            CounterExampleCase(
                expression=expression,
                error_type=first["error_key"],
                error_message=report.errors[0],
                fix_hint=first["fix_hint"],
            )
        )

    if not cases:
        raise RuntimeError("Failed to build counterexamples pack: no invalid cases were captured")

    return FastExprCounterExamplesPack(
        generated_at=utc_now_iso(),
        cases=cases,
    )


def _build_visual_pack(
    *,
    operators: list[OperatorSignatureEntry],
    examples: list[FastExprExampleEntry],
) -> FastExprVisualPack:
    cards: list[VisualOperatorCard] = []
    for operator in operators:
        category = operator.category or "Uncategorized"
        cards.append(
            VisualOperatorCard(
                name=operator.name,
                category=category,
                scope=operator.scope,
                signature=operator.definition or f"{operator.name}(...)",
                display=_display_style_for_operator(category),
                tips=_tips_for_operator(operator.name, category),
            )
        )

    error_taxonomy = [
        {
            "error_key": row["error_key"],
            "match_pattern": row["match_pattern"],
            "severity": row["severity"],
            "fix_hint": row["fix_hint"],
        }
        for row in VALIDATION_ERROR_TAXONOMY
    ]

    example_cards = [
        VisualExampleCard(
            expression=entry.expression,
            tags=entry.tags,
            quality_flags={"validation_passed": True, "counterexample": False},
        )
        for entry in examples
    ]

    return FastExprVisualPack(
        generated_at=utc_now_iso(),
        operators=cards,
        error_taxonomy=error_taxonomy,
        example_cards=example_cards,
    )


def _example_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [
        {
            "expression": "rank(ts_delta(log(close), 5))",
            "tags": ["starter", "rulebook-aligned", "price-volume", "timeseries-window"],
            "source": "rulebook_template",
        },
        {
            "expression": "zscore(ts_mean(bookvalue_ps, 20))",
            "tags": ["fundamental", "cross-sectional-normalization", "timeseries-window"],
            "source": "rulebook_template",
        },
        {
            "expression": "group_neutralize(rank(close), sector)",
            "tags": ["group-neutralization", "market-neutralization", "rulebook-aligned"],
            "source": "rulebook_template",
        },
        {
            "expression": "hump(ts_decay_linear(rank(returns), 5), 0.001)",
            "tags": ["turnover-control", "execution-control", "rulebook-aligned"],
            "source": "rulebook_template",
        },
        {
            "expression": "vec_avg(absolute_price_change_today)",
            "tags": ["vector-aggregated", "type-safe-vector", "rulebook-aligned"],
            "source": "rulebook_template",
        },
    ]

    fixture_expr = _expression_from_alpha_fixture(Path("docs/artifacts/fixtures/alpha.sample.json"))
    if fixture_expr:
        candidates.append(
            {
                "expression": fixture_expr,
                "tags": ["fixture", "starter"],
                "source": "fixtures.alpha.sample",
            }
        )
    return candidates


def _expression_from_alpha_fixture(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    regular = payload.get("regular")
    if isinstance(regular, dict):
        code = regular.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


def _build_field_subcategory_lookup(
    *,
    fields: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
) -> dict[str, str]:
    dataset_to_subcategory: dict[str, str] = {}
    for dataset in datasets:
        dataset_id = str(dataset.get("id") or "")
        if not dataset_id:
            continue
        raw = _parse_raw_json(dataset.get("raw_json"))
        subcategory = raw.get("subcategory") if isinstance(raw.get("subcategory"), dict) else {}
        sub_id = str(subcategory.get("id") or "unknown")
        dataset_to_subcategory[dataset_id] = sub_id

    out: dict[str, str] = {}
    for field in fields:
        field_id = str(field.get("id") or "")
        dataset_id = str(field.get("dataset_id") or "")
        if not field_id:
            continue
        out[field_id] = dataset_to_subcategory.get(dataset_id, "unknown")
    return out


def _extract_allowed_nodes_from_raw_options(payload: dict[str, Any]) -> dict[str, Any]:
    return (
        payload.get("actions", {})
        .get("POST", {})
        .get("settings", {})
        .get("children", {})
    )


def _extract_choice_values(choices: Any) -> list[Any]:
    values: list[Any] = []
    _collect_choice_values(choices, values)
    return _dedupe_values(values)


def _collect_choice_values(node: Any, out: list[Any]) -> None:
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and "value" in item:
                out.append(item["value"])
            else:
                _collect_choice_values(item, out)
        return
    if isinstance(node, dict):
        if "value" in node and len(node.keys()) <= 3:
            out.append(node["value"])
            return
        for value in node.values():
            _collect_choice_values(value, out)
        return
    if node is not None:
        out.append(node)


def _dedupe_values(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _rule_tags_for_expression(expression: str) -> list[str]:
    lower = expression.lower()
    tags: list[str] = ["regular-signal"]
    if "ts_" in lower:
        tags.append("timeseries-window")
    if "group_" in lower:
        tags.append("group-neutralization")
    if "vec_" in lower:
        tags.append("vector-aggregated")
    if "rank(" in lower or "zscore(" in lower:
        tags.append("cross-sectional-normalization")
    if "trade_when(" in lower or "if_else(" in lower:
        tags.append("conditional-logic")
    if "hump(" in lower or "ts_decay_linear(" in lower:
        tags.append("turnover-control")
    if "bucket(" in lower:
        tags.append("group-bucketing")
    return _merge_unique(tags, [])


def _display_style_for_operator(category: str) -> dict[str, str]:
    key = category.strip().lower()
    mapping = {
        "time series": {"group": "timeseries", "badge_color": "cyan", "complexity": "medium"},
        "cross sectional": {"group": "cross_sectional", "badge_color": "amber", "complexity": "low"},
        "group": {"group": "group_ops", "badge_color": "orange", "complexity": "medium"},
        "transform": {"group": "transform", "badge_color": "blue", "complexity": "low"},
        "vector": {"group": "vector_ops", "badge_color": "green", "complexity": "medium"},
        "logical": {"group": "logical", "badge_color": "rose", "complexity": "medium"},
    }
    return mapping.get(key, {"group": "misc", "badge_color": "slate", "complexity": "medium"})


def _tips_for_operator(name: str, category: str) -> list[str]:
    lname = name.lower()
    lcat = category.lower()
    if lname.startswith("ts_"):
        return [
            "MATRIX 필드와 lookback(d) 인자를 함께 사용",
            "결측치가 많은 필드는 ts_backfill 후 결합 검토",
        ]
    if lname.startswith("group_") or lname == "group_neutralize":
        return [
            "GROUP + MATRIX 조합을 맞춰야 타입 위반을 피함",
            "GROUP 필드가 없으면 bucket(rank(cap)) 패턴 고려",
        ]
    if lname.startswith("vec_"):
        return [
            "VECTOR 필드는 vec_ 계열로 집계 후 후속 연산에 전달",
            "vec_ 결과를 rank/zscore와 조합해 스케일 안정화",
        ]
    if lname in {"rank", "zscore", "quantile", "scale"}:
        return [
            "동일 단계에서 중복 정규화를 과도하게 쌓지 않기",
            "단위가 다른 필드 결합 전 정규화 우선 적용",
        ]
    if lname in {"trade_when", "if_else"}:
        return [
            "조건식 중첩을 최소화해 디버깅 가능성 유지",
            "entry/exit 조건의 의미를 generation_notes에 남기기",
        ]
    if lname in {"hump", "ts_decay_linear"}:
        return [
            "turnover 제어 연산은 신호 생성 이후 후단에 배치",
            "감쇠 강도가 높을수록 반응성이 낮아질 수 있음",
        ]
    if lcat == "time series":
        return [
            "시계열 lookback은 신호 시간축과 일치시킬 것",
            "이상치/결측이 많은 경우 robust 연산자 우선 고려",
        ]
    return [
        "operators metadata의 signature/scope를 우선 준수",
        "retrieval pack 후보 내 field/operator만 조합",
    ]


def _parse_scope(scope: Any) -> list[str]:
    if scope is None:
        return []
    if isinstance(scope, list):
        return [str(x).strip() for x in scope if str(x).strip()]
    if isinstance(scope, str):
        return [x.strip() for x in scope.split(",") if x.strip()]
    return [str(scope)]


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _merge_unique(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*first, *second]:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _parse_raw_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}
