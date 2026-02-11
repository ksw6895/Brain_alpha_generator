"""Build retrieval packs with Top-K gating for LLM input control."""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..constants import DEFAULT_META_DIR
from ..schemas import IdeaSpec, SimulationTarget
from ..storage.sqlite_store import MetadataStore
from .keyword import KeywordRetriever


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
ALLOWED_FIELD_TYPES = {"MATRIX", "GROUP", "VECTOR"}


class RetrievalLaneBudget(BaseModel):
    subcategories: int = 4
    datasets: int = 14
    fields: int = 60
    operators: int = 48


class RetrievalExpansionPolicy(BaseModel):
    enabled: bool = True
    trigger_on_repeated_validation_error: int = 2
    topk_expand_factor: float = 1.5


class RetrievalBudgetConfig(BaseModel):
    exploit_ratio: float = 0.7
    explore_ratio: float = 0.3
    exploit: RetrievalLaneBudget = Field(default_factory=RetrievalLaneBudget)
    explore: RetrievalLaneBudget = Field(
        default_factory=lambda: RetrievalLaneBudget(
            subcategories=1,
            datasets=3,
            fields=12,
            operators=12,
        )
    )
    expansion_policy: RetrievalExpansionPolicy = Field(default_factory=RetrievalExpansionPolicy)


class LaneSelection(BaseModel):
    field_ids: list[str] = Field(default_factory=list)
    operator_names: list[str] = Field(default_factory=list)


class VisualGraphNode(BaseModel):
    id: str
    type: Literal["idea", "subcategory", "dataset", "field", "operator"]
    label: str
    lane: Literal["exploit", "explore"]
    state: Literal["searching", "selected", "dropped"]
    score: float


class VisualGraphEdge(BaseModel):
    source: str
    target: str
    kind: Literal["retrieval_match", "contains_dataset", "contains_field", "supports_operator"]
    weight: float


class VisualGraph(BaseModel):
    version: str = "v1"
    nodes: list[VisualGraphNode] = Field(default_factory=list)
    edges: list[VisualGraphEdge] = Field(default_factory=list)


class DatasetCandidate(BaseModel):
    id: str
    name: str
    subcategory_id: str
    lane: Literal["exploit", "explore"]
    score: float


class FieldCandidate(BaseModel):
    id: str
    dataset_id: str
    type: str
    lane: Literal["exploit", "explore"]
    score: float


class OperatorCandidate(BaseModel):
    name: str
    definition: str | None = None
    scope: list[str] = Field(default_factory=list)
    category: str | None = None
    lane: Literal["exploit", "explore"]
    score: float


class RetrievalTokenEstimate(BaseModel):
    input_chars: int
    input_tokens_rough: int


class RetrievalTelemetry(BaseModel):
    retrieval_ms: int
    candidate_counts: dict[str, int]


class RetrievalContextGuard(BaseModel):
    full_metadata_blocked: bool
    rules: list[str]
    max_items: dict[str, int]


class RetrievalPack(BaseModel):
    idea_id: str
    query: str
    target: SimulationTarget
    selected_subcategories: list[str] = Field(default_factory=list)
    candidate_datasets: list[DatasetCandidate] = Field(default_factory=list)
    candidate_fields: list[FieldCandidate] = Field(default_factory=list)
    candidate_operators: list[OperatorCandidate] = Field(default_factory=list)
    lanes: dict[str, LaneSelection] = Field(default_factory=dict)
    visual_graph: VisualGraph
    token_estimate: RetrievalTokenEstimate
    budget_policy: dict[str, Any]
    expansion_policy: dict[str, Any]
    context_guard: RetrievalContextGuard
    telemetry: RetrievalTelemetry


class RetrievalPackBuilder:
    """Create bounded retrieval packs from local metadata store."""

    def __init__(
        self,
        *,
        store: MetadataStore,
        budget: RetrievalBudgetConfig | None = None,
        meta_dir: str | Path = DEFAULT_META_DIR,
    ) -> None:
        self.store = store
        self.budget = budget or RetrievalBudgetConfig()
        self.meta_dir = Path(meta_dir)
        self.retriever = KeywordRetriever(store)
        self.subcategory_glossary = _load_subcategory_glossary(self.meta_dir)

    def build(self, idea: IdeaSpec, *, query_override: str | None = None) -> RetrievalPack:
        start = time.perf_counter()
        query = (query_override or _build_query(idea)).strip()
        if not query:
            query = idea.hypothesis.strip() or idea.idea_id

        datasets = _load_dataset_rows(self.store, target=idea.target)
        if not datasets:
            raise RuntimeError(
                "No datasets available for retrieval pack. Run sync-metadata first for target "
                f"{idea.target.region}/{idea.target.delay}/{idea.target.universe}."
            )

        subcategory_scores = _rank_subcategories(query, datasets, self.subcategory_glossary)
        exploit_subcats, explore_subcats = _select_subcategories(subcategory_scores, self.budget)
        selected_subcategories = _merge_unique(exploit_subcats, explore_subcats)

        datasets_by_lane = self._select_datasets_by_lane(
            query=query,
            datasets=datasets,
            exploit_subcats=exploit_subcats,
            explore_subcats=explore_subcats,
        )
        fields_by_lane = self._select_fields_by_lane(
            query=query,
            target=idea.target,
            dataset_ids_by_lane={
                "exploit": [x.id for x in datasets_by_lane["exploit"]],
                "explore": [x.id for x in datasets_by_lane["explore"]],
            },
        )
        operators_by_lane = self._select_operators_by_lane(query=query)

        candidate_datasets = _merge_unique_models(datasets_by_lane["exploit"], datasets_by_lane["explore"], key="id")
        candidate_fields = _merge_unique_models(fields_by_lane["exploit"], fields_by_lane["explore"], key="id")
        candidate_operators = _merge_unique_models(
            operators_by_lane["exploit"],
            operators_by_lane["explore"],
            key="name",
        )

        lanes = {
            "exploit": LaneSelection(
                field_ids=[x.id for x in fields_by_lane["exploit"]],
                operator_names=[x.name for x in operators_by_lane["exploit"]],
            ),
            "explore": LaneSelection(
                field_ids=[x.id for x in fields_by_lane["explore"]],
                operator_names=[x.name for x in operators_by_lane["explore"]],
            ),
        }

        visual_graph = _build_visual_graph(
            idea=idea,
            query=query,
            subcategory_scores=subcategory_scores,
            exploit_subcats=exploit_subcats,
            explore_subcats=explore_subcats,
            datasets=candidate_datasets,
            fields=candidate_fields,
            operators=candidate_operators,
        )

        guard = RetrievalContextGuard(
            full_metadata_blocked=True,
            rules=[
                "Use only selected_subcategories and candidate_* lists in downstream prompts.",
                "Do not include full operators/datasets/data-fields dumps in prompts.",
                "If repeated validation errors hit threshold, expand retrieval via expansion_policy.",
            ],
            max_items={
                "datasets": self.budget.exploit.datasets + self.budget.explore.datasets,
                "fields": self.budget.exploit.fields + self.budget.explore.fields,
                "operators": self.budget.exploit.operators + self.budget.explore.operators,
            },
        )

        token_estimate = _estimate_tokens(
            {
                "query": query,
                "target": idea.target.model_dump(mode="python"),
                "selected_subcategories": selected_subcategories,
                "candidate_datasets": [x.model_dump(mode="python") for x in candidate_datasets],
                "candidate_fields": [x.model_dump(mode="python") for x in candidate_fields],
                "candidate_operators": [x.model_dump(mode="python") for x in candidate_operators],
                "context_guard": guard.model_dump(mode="python"),
            }
        )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        telemetry = RetrievalTelemetry(
            retrieval_ms=elapsed_ms,
            candidate_counts={
                "subcategories": len(selected_subcategories),
                "datasets": len(candidate_datasets),
                "fields": len(candidate_fields),
                "operators": len(candidate_operators),
            },
        )

        return RetrievalPack(
            idea_id=idea.idea_id,
            query=query,
            target=idea.target,
            selected_subcategories=selected_subcategories,
            candidate_datasets=candidate_datasets,
            candidate_fields=candidate_fields,
            candidate_operators=candidate_operators,
            lanes=lanes,
            visual_graph=visual_graph,
            token_estimate=token_estimate,
            budget_policy={
                "exploit_ratio": self.budget.exploit_ratio,
                "explore_ratio": self.budget.explore_ratio,
                "exploit": self.budget.exploit.model_dump(mode="python"),
                "explore": self.budget.explore.model_dump(mode="python"),
            },
            expansion_policy=self.budget.expansion_policy.model_dump(mode="python"),
            context_guard=guard,
            telemetry=telemetry,
        )

    def _select_datasets_by_lane(
        self,
        *,
        query: str,
        datasets: list[dict[str, Any]],
        exploit_subcats: list[str],
        explore_subcats: list[str],
    ) -> dict[str, list[DatasetCandidate]]:
        max_k = max(200, self.budget.exploit.datasets + self.budget.explore.datasets + 50)
        dataset_hits = self.retriever.retrieve_datasets(query, k=max_k)
        score_map = {hit.item_id: float(hit.score) for hit in dataset_hits}

        # Additional quality term to stabilize ranking when keyword scores tie.
        quality_scores = {
            row["id"]: (
                _to_float(row.get("valueScore")) * 4.0
                + _to_float(row.get("coverage")) * 2.0
                + _to_float(row.get("fieldCount")) * 0.01
                + _to_float(row.get("userCount")) * 0.001
            )
            for row in datasets
            if row.get("id")
        }
        quality_norm = _normalize_map(quality_scores)
        hit_norm = _normalize_map(score_map)

        by_id = {str(row.get("id")): row for row in datasets if row.get("id")}

        def lane_pick(subcats: list[str], k: int, lane: Literal["exploit", "explore"]) -> list[DatasetCandidate]:
            rows = [row for row in datasets if row.get("subcategory_id") in set(subcats)]
            if not rows:
                rows = datasets
            ranked = sorted(
                rows,
                key=lambda row: (
                    0.8 * hit_norm.get(str(row.get("id")), 0.0) + 0.2 * quality_norm.get(str(row.get("id")), 0.0),
                    _to_float(row.get("fieldCount")),
                ),
                reverse=True,
            )
            out: list[DatasetCandidate] = []
            for row in ranked:
                ds_id = str(row.get("id", ""))
                if not ds_id:
                    continue
                score = 0.8 * hit_norm.get(ds_id, 0.0) + 0.2 * quality_norm.get(ds_id, 0.0)
                out.append(
                    DatasetCandidate(
                        id=ds_id,
                        name=str(row.get("name") or ds_id),
                        subcategory_id=str(row.get("subcategory_id") or "unknown"),
                        lane=lane,
                        score=round(_clip01(score), 4),
                    )
                )
                if len(out) >= k:
                    break
            return out

        exploit = lane_pick(exploit_subcats, self.budget.exploit.datasets, "exploit")
        explore = lane_pick(explore_subcats, self.budget.explore.datasets, "explore")

        if not explore:
            fallback_rows = sorted(
                datasets,
                key=lambda row: (_to_float(row.get("fieldCount")), -_to_float(row.get("valueScore"))),
            )
            for row in fallback_rows:
                ds_id = str(row.get("id", ""))
                if not ds_id:
                    continue
                if ds_id in {x.id for x in exploit}:
                    continue
                explore.append(
                    DatasetCandidate(
                        id=ds_id,
                        name=str(row.get("name") or ds_id),
                        subcategory_id=str(row.get("subcategory_id") or "unknown"),
                        lane="explore",
                        score=round(quality_norm.get(ds_id, 0.0), 4),
                    )
                )
                if len(explore) >= self.budget.explore.datasets:
                    break

        # Ensure selected dataset rows still exist in source map.
        exploit = [x for x in exploit if x.id in by_id]
        explore = [x for x in explore if x.id in by_id]
        return {"exploit": exploit, "explore": explore}

    def _select_fields_by_lane(
        self,
        *,
        query: str,
        target: SimulationTarget,
        dataset_ids_by_lane: dict[str, list[str]],
    ) -> dict[str, list[FieldCandidate]]:
        total_k = self.budget.exploit.fields + self.budget.explore.fields
        hit_k = min(3000, max(300, total_k * 4))
        field_hits = self.retriever.retrieve_data_fields(query, k=hit_k)
        hit_score_map = {hit.item_id: float(hit.score) for hit in field_hits}
        hit_score_norm = _normalize_map(hit_score_map)

        # Load all fields once for fallback and target filtering.
        field_rows = self.store.list_data_fields()
        filtered_rows = []
        for row in field_rows:
            if str(row.get("region") or "").upper() != target.region.upper():
                continue
            if int(row.get("delay") or target.delay) != target.delay:
                continue
            if str(row.get("universe") or "").upper() != target.universe.upper():
                continue
            field_id = str(row.get("id") or "")
            dataset_id = str(row.get("dataset_id") or "")
            if not field_id or not dataset_id:
                continue
            ftype = str(row.get("type") or "").upper()
            if ftype not in ALLOWED_FIELD_TYPES:
                continue
            filtered_rows.append(row)

        # Reusable quality score for fallback ordering.
        quality = {
            str(row.get("id")): _to_float(row.get("alphaCount")) * 0.7 + _to_float(row.get("coverage")) * 0.3
            for row in filtered_rows
            if row.get("id")
        }
        quality_norm = _normalize_map(quality)

        def lane_pick(lane: Literal["exploit", "explore"], k: int) -> list[FieldCandidate]:
            lane_dataset_ids = set(dataset_ids_by_lane.get(lane, []))
            if not lane_dataset_ids:
                lane_dataset_ids = set(str(row.get("dataset_id")) for row in filtered_rows if row.get("dataset_id"))

            lane_rows = [row for row in filtered_rows if str(row.get("dataset_id")) in lane_dataset_ids]
            ranked = sorted(
                lane_rows,
                key=lambda row: (
                    0.85 * hit_score_norm.get(str(row.get("id")), 0.0) + 0.15 * quality_norm.get(str(row.get("id")), 0.0),
                    _type_priority(str(row.get("type") or "")),
                ),
                reverse=True,
            )

            out: list[FieldCandidate] = []
            seen: set[str] = set()
            for row in ranked:
                field_id = str(row.get("id") or "")
                if not field_id or field_id in seen:
                    continue
                seen.add(field_id)
                score = 0.85 * hit_score_norm.get(field_id, 0.0) + 0.15 * quality_norm.get(field_id, 0.0)
                out.append(
                    FieldCandidate(
                        id=field_id,
                        dataset_id=str(row.get("dataset_id") or ""),
                        type=str(row.get("type") or ""),
                        lane=lane,
                        score=round(_clip01(score), 4),
                    )
                )
                if len(out) >= k:
                    break
            return out

        exploit = lane_pick("exploit", self.budget.exploit.fields)
        explore = lane_pick("explore", self.budget.explore.fields)

        if not explore:
            for row in sorted(filtered_rows, key=lambda x: _to_float(x.get("alphaCount"))):
                field_id = str(row.get("id") or "")
                if not field_id:
                    continue
                if field_id in {x.id for x in exploit}:
                    continue
                explore.append(
                    FieldCandidate(
                        id=field_id,
                        dataset_id=str(row.get("dataset_id") or ""),
                        type=str(row.get("type") or ""),
                        lane="explore",
                        score=round(quality_norm.get(field_id, 0.0), 4),
                    )
                )
                if len(explore) >= self.budget.explore.fields:
                    break

        return {"exploit": exploit, "explore": explore}

    def _select_operators_by_lane(self, *, query: str) -> dict[str, list[OperatorCandidate]]:
        total_k = self.budget.exploit.operators + self.budget.explore.operators
        hit_k = min(1000, max(100, total_k * 5))
        hits = self.retriever.retrieve_operators(query, k=hit_k)
        hit_score_map = {hit.item_id: float(hit.score) for hit in hits}
        hit_norm = _normalize_map(hit_score_map)

        operators = self.store.list_operators()
        by_name = {str(row.get("name")): row for row in operators if row.get("name")}
        category_counts = _operator_category_counts(operators)

        ranked = sorted(
            by_name.keys(),
            key=lambda name: (hit_norm.get(name, 0.0), -1 * category_counts.get(str(by_name[name].get("category")), 1)),
            reverse=True,
        )

        exploit_names = ranked[: self.budget.exploit.operators]
        used = set(exploit_names)

        explore_candidates = sorted(
            [name for name in ranked if name not in used],
            key=lambda name: (
                category_counts.get(str(by_name[name].get("category")), 1),
                -hit_norm.get(name, 0.0),
            ),
        )
        explore_names = explore_candidates[: self.budget.explore.operators]

        if not explore_names:
            explore_names = [name for name in ranked if name not in used][: max(1, self.budget.explore.operators)]

        def to_model(names: list[str], lane: Literal["exploit", "explore"]) -> list[OperatorCandidate]:
            out: list[OperatorCandidate] = []
            for name in names:
                row = by_name.get(name)
                if not row:
                    continue
                out.append(
                    OperatorCandidate(
                        name=name,
                        definition=str(row.get("definition")) if row.get("definition") else None,
                        scope=_parse_scope_list(row.get("scope")),
                        category=str(row.get("category")) if row.get("category") else None,
                        lane=lane,
                        score=round(_clip01(hit_norm.get(name, 0.0)), 4),
                    )
                )
            return out

        return {
            "exploit": to_model(exploit_names, "exploit"),
            "explore": to_model(explore_names, "explore"),
        }


def load_retrieval_budget(path: str | Path | None = None) -> RetrievalBudgetConfig:
    """Load retrieval budget config from JSON or return defaults."""
    if path is None:
        return RetrievalBudgetConfig()
    p = Path(path)
    if not p.exists():
        return RetrievalBudgetConfig()
    payload = json.loads(p.read_text(encoding="utf-8"))
    return RetrievalBudgetConfig.model_validate(payload)


def build_retrieval_pack(
    *,
    idea: IdeaSpec,
    store: MetadataStore,
    budget: RetrievalBudgetConfig | None = None,
    meta_dir: str | Path = DEFAULT_META_DIR,
    query_override: str | None = None,
) -> RetrievalPack:
    """Convenience wrapper for one-shot retrieval pack build."""
    builder = RetrievalPackBuilder(store=store, budget=budget, meta_dir=meta_dir)
    return builder.build(idea, query_override=query_override)


def summarize_pack_for_event(pack: RetrievalPack) -> dict[str, Any]:
    """Build compact event payload for retrieval pack completion."""
    return {
        "idea_id": pack.idea_id,
        "query": pack.query,
        "selected_subcategories": pack.selected_subcategories,
        "candidate_counts": pack.telemetry.candidate_counts,
        "token_estimate": pack.token_estimate.model_dump(mode="python"),
        "budget_policy": pack.budget_policy,
        "expansion_policy": pack.expansion_policy,
    }


def _build_query(idea: IdeaSpec) -> str:
    parts = [x.strip() for x in idea.keywords_for_retrieval if x and x.strip()]
    if parts:
        return " ".join(parts)
    return idea.hypothesis


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def _idf_weighted_overlap(
    query_tokens: list[str],
    doc_tokens: list[str],
    *,
    corpus_df: dict[str, int],
    corpus_size: int,
) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_set = set(doc_tokens)
    score = 0.0
    for token in query_tokens:
        if token not in doc_set:
            continue
        df = corpus_df.get(token, 1)
        score += math.log((corpus_size + 1) / (df + 1)) + 1.0
    return score


def _rank_subcategories(
    query: str,
    datasets: list[dict[str, Any]],
    glossary: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_subcat: dict[str, dict[str, Any]] = {}
    for row in datasets:
        sub_id = str(row.get("subcategory_id") or "unknown")
        if sub_id not in by_subcat:
            by_subcat[sub_id] = {
                "id": sub_id,
                "name": str(row.get("subcategory_name") or sub_id),
                "category": str(row.get("category_name") or "uncategorized"),
                "dataset_count": 0,
                "meaning": "",
            }
        by_subcat[sub_id]["dataset_count"] += 1

    for sub_id, card in by_subcat.items():
        if sub_id in glossary:
            ext = glossary[sub_id]
            card["meaning"] = str(ext.get("meaning") or "")
            card["name"] = str(ext.get("name") or card["name"])

    docs = []
    ids = []
    for card in by_subcat.values():
        text = " ".join(
            [
                str(card.get("id") or ""),
                str(card.get("name") or ""),
                str(card.get("category") or ""),
                str(card.get("meaning") or ""),
            ]
        )
        ids.append(str(card["id"]))
        docs.append(_tokenize(text))

    query_tokens = _tokenize(query)
    if not ids:
        return []
    if not query_tokens:
        return sorted(by_subcat.values(), key=lambda x: x["dataset_count"], reverse=True)

    df: dict[str, int] = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1

    scored: list[dict[str, Any]] = []
    for sub_id, doc_tokens in zip(ids, docs):
        score = _idf_weighted_overlap(query_tokens, doc_tokens, corpus_df=df, corpus_size=len(docs))
        card = by_subcat[sub_id]
        scored.append({**card, "score": score})
    scored.sort(key=lambda x: (x.get("score", 0.0), x.get("dataset_count", 0)), reverse=True)
    return scored


def _select_subcategories(
    ranked_subcats: list[dict[str, Any]],
    budget: RetrievalBudgetConfig,
) -> tuple[list[str], list[str]]:
    exploit_k = max(1, budget.exploit.subcategories)
    explore_k = max(1, budget.explore.subcategories)

    exploit: list[str] = []
    for row in ranked_subcats:
        sub_id = str(row.get("id") or "")
        if not sub_id:
            continue
        exploit.append(sub_id)
        if len(exploit) >= exploit_k:
            break

    remaining = [row for row in ranked_subcats if str(row.get("id") or "") not in set(exploit)]
    remaining.sort(
        key=lambda row: (
            row.get("dataset_count", 0),  # low-frequency first
            -1 * _to_float(row.get("score")),
        )
    )
    explore: list[str] = []
    for row in remaining:
        sub_id = str(row.get("id") or "")
        if not sub_id:
            continue
        explore.append(sub_id)
        if len(explore) >= explore_k:
            break

    if not explore and exploit:
        explore = [exploit[-1]]
    return exploit, explore


def _build_visual_graph(
    *,
    idea: IdeaSpec,
    query: str,
    subcategory_scores: list[dict[str, Any]],
    exploit_subcats: list[str],
    explore_subcats: list[str],
    datasets: list[DatasetCandidate],
    fields: list[FieldCandidate],
    operators: list[OperatorCandidate],
) -> VisualGraph:
    nodes: list[VisualGraphNode] = []
    edges: list[VisualGraphEdge] = []

    nodes.append(
        VisualGraphNode(
            id=f"idea:{idea.idea_id}",
            type="idea",
            label=query[:120] or idea.idea_id,
            lane="exploit",
            state="selected",
            score=1.0,
        )
    )

    subscore = {str(x.get("id")): _to_float(x.get("score")) for x in subcategory_scores}
    subscore_norm = _normalize_map(subscore)
    exploit_set = set(exploit_subcats)
    explore_set = set(explore_subcats)
    selected_set = set(exploit_subcats) | set(explore_subcats)

    for row in subcategory_scores:
        sub_id = str(row.get("id") or "")
        if not sub_id:
            continue
        if sub_id in exploit_set:
            lane: Literal["exploit", "explore"] = "exploit"
            state: Literal["selected", "searching", "dropped"] = "selected"
        elif sub_id in explore_set:
            lane = "explore"
            state = "selected"
        else:
            # Keep a small set of dropped nodes for UI context.
            if len([n for n in nodes if n.state == "dropped" and n.type == "subcategory"]) >= 3:
                continue
            lane = "explore"
            state = "dropped"

        label = str(row.get("name") or sub_id)
        nodes.append(
            VisualGraphNode(
                id=f"subcategory:{sub_id}",
                type="subcategory",
                label=label,
                lane=lane,
                state=state,
                score=round(_clip01(subscore_norm.get(sub_id, 0.0)), 4),
            )
        )
        weight = subscore_norm.get(sub_id, 0.0) if sub_id in selected_set else 0.2
        edges.append(
            VisualGraphEdge(
                source=f"idea:{idea.idea_id}",
                target=f"subcategory:{sub_id}",
                kind="retrieval_match",
                weight=round(_clip01(weight), 4),
            )
        )

    for ds in datasets:
        nodes.append(
            VisualGraphNode(
                id=f"dataset:{ds.id}",
                type="dataset",
                label=ds.name,
                lane=ds.lane,
                state="selected",
                score=round(_clip01(ds.score), 4),
            )
        )
        edges.append(
            VisualGraphEdge(
                source=f"subcategory:{ds.subcategory_id}",
                target=f"dataset:{ds.id}",
                kind="contains_dataset",
                weight=round(_clip01(ds.score), 4),
            )
        )

    for i, field in enumerate(fields):
        field_state: Literal["selected", "searching", "dropped"] = "searching" if i < 20 else "selected"
        nodes.append(
            VisualGraphNode(
                id=f"field:{field.id}",
                type="field",
                label=field.id,
                lane=field.lane,
                state=field_state,
                score=round(_clip01(field.score), 4),
            )
        )
        edges.append(
            VisualGraphEdge(
                source=f"dataset:{field.dataset_id}",
                target=f"field:{field.id}",
                kind="contains_field",
                weight=round(_clip01(field.score), 4),
            )
        )

    for op in operators:
        nodes.append(
            VisualGraphNode(
                id=f"operator:{op.name}",
                type="operator",
                label=op.name,
                lane=op.lane,
                state="selected",
                score=round(_clip01(op.score), 4),
            )
        )

    # Connect top fields and operators within each lane.
    for lane in ("exploit", "explore"):
        lane_fields = [x for x in fields if x.lane == lane][: min(8, len(fields))]
        lane_ops = [x for x in operators if x.lane == lane][: min(8, len(operators))]
        for field in lane_fields:
            for op in lane_ops:
                weight = 0.5 * field.score + 0.5 * op.score
                edges.append(
                    VisualGraphEdge(
                        source=f"field:{field.id}",
                        target=f"operator:{op.name}",
                        kind="supports_operator",
                        weight=round(_clip01(weight), 4),
                    )
                )

    # Deduplicate graph entries.
    dedup_nodes = {node.id: node for node in nodes}
    edge_key = lambda e: (e.source, e.target, e.kind)
    dedup_edges: dict[tuple[str, str, str], VisualGraphEdge] = {}
    for edge in edges:
        dedup_edges[edge_key(edge)] = edge

    return VisualGraph(
        nodes=list(dedup_nodes.values()),
        edges=list(dedup_edges.values()),
    )


def _estimate_tokens(payload: dict[str, Any]) -> RetrievalTokenEstimate:
    text = json.dumps(payload, ensure_ascii=False)
    chars = len(text)
    # Conservative rough conversion used for gating, not billing.
    rough_tokens = max(1, int(chars / 4))
    return RetrievalTokenEstimate(input_chars=chars, input_tokens_rough=rough_tokens)


def _load_dataset_rows(store: MetadataStore, *, target: SimulationTarget) -> list[dict[str, Any]]:
    rows = store.list_datasets()
    out: list[dict[str, Any]] = []
    for row in rows:
        region = str(row.get("region") or "").upper()
        universe = str(row.get("universe") or "").upper()
        delay = int(row.get("delay") or target.delay)
        if region != target.region.upper():
            continue
        if universe != target.universe.upper():
            continue
        if delay != target.delay:
            continue

        raw = _parse_json_row(row.get("raw_json"))
        subcategory = raw.get("subcategory") if isinstance(raw.get("subcategory"), dict) else {}
        category = raw.get("category") if isinstance(raw.get("category"), dict) else {}
        out.append(
            {
                "id": str(row.get("id") or ""),
                "name": row.get("name"),
                "description": row.get("description"),
                "coverage": row.get("coverage"),
                "valueScore": row.get("valueScore"),
                "fieldCount": row.get("fieldCount"),
                "userCount": row.get("userCount"),
                "subcategory_id": str(subcategory.get("id") or "unknown"),
                "subcategory_name": str(subcategory.get("name") or "unknown"),
                "category_name": str(category.get("name") or "uncategorized"),
            }
        )
    return [x for x in out if x.get("id")]


def _parse_json_row(raw_json: Any) -> dict[str, Any]:
    if not raw_json:
        return {}
    if isinstance(raw_json, dict):
        return raw_json
    if not isinstance(raw_json, str):
        return {}
    try:
        payload = json.loads(raw_json)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _load_subcategory_glossary(meta_dir: Path) -> dict[str, dict[str, Any]]:
    path = meta_dir / "index" / "datasets_by_subcategory.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        sub_id = str(row.get("id") or "")
        if not sub_id:
            continue
        out[sub_id] = row
    return out


def _parse_scope_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(value)]


def _normalize_map(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    max_v = max(values.values())
    min_v = min(values.values())
    if max_v <= min_v:
        return {k: 1.0 if v > 0 else 0.0 for k, v in values.items()}
    return {k: _clip01((v - min_v) / (max_v - min_v)) for k, v in values.items()}


def _merge_unique(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*first, *second]:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _merge_unique_models(first: list[BaseModel], second: list[BaseModel], *, key: str) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in [*first, *second]:
        value = str(getattr(item, key))
        if value in seen:
            continue
        seen.add(value)
        out.append(item)
    return out


def _operator_category_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "uncategorized")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _type_priority(field_type: str) -> int:
    value = str(field_type or "").upper()
    if value == "MATRIX":
        return 3
    if value == "GROUP":
        return 2
    if value == "VECTOR":
        return 1
    return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _clip01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return float(value)
