"""Build compact metadata indexes for agent-friendly retrieval."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..utils.filesystem import utc_now_iso, write_json

CATEGORY_MEANINGS: dict[str, str] = {
    "analyst": "Sell-side or crowdsourced analyst estimates, ratings, and related estimate revisions.",
    "earnings": "Earnings events, surprises, and earnings estimate dynamics.",
    "fundamental": "Company fundamental/accounting statement features and derived accounting models.",
    "imbalance": "Order imbalance and microstructure imbalance signals.",
    "institutions": "Institutional ownership and positioning related data.",
    "insiders": "Insider trading and insider ownership changes.",
    "macro": "Macroeconomic activity and broad macro condition indicators.",
    "model": "Prebuilt model outputs/factors (valuation, risk, technical, NLP, ML).",
    "news": "News event and text-derived features, including sentiment transformations.",
    "option": "Options market features such as implied vol and option analytics.",
    "other": "Miscellaneous alternative datasets that do not fit a primary bucket.",
    "pv": "Core market price-volume data and price-volume relationships.",
    "risk": "Risk model exposures, risk factors, and risk-oriented model outputs.",
    "sentiment": "Alternative sentiment-oriented datasets outside primary news buckets.",
    "shortinterest": "Short selling interest and borrow pressure related features.",
    "socialmedia": "Social-media sourced signals and social attention proxies.",
}

CATEGORY_AGENT_HINTS: dict[str, dict[str, Any]] = {
    "pv": {"signal_horizon": "short_to_medium", "operator_families": ["ts_*", "rank", "zscore", "group_*"]},
    "fundamental": {"signal_horizon": "medium_to_long", "operator_families": ["ts_*", "rank", "group_*"]},
    "news": {"signal_horizon": "short_to_medium", "operator_families": ["ts_*", "rank", "signed_power"]},
    "sentiment": {"signal_horizon": "short_to_medium", "operator_families": ["ts_*", "zscore", "group_rank"]},
    "model": {"signal_horizon": "medium", "operator_families": ["rank", "zscore", "group_*"]},
    "risk": {"signal_horizon": "medium", "operator_families": ["group_neutralize", "zscore", "ts_*"]},
}


def build_metadata_indexes(
    *,
    meta_dir: str | Path,
    datasets: list[dict[str, Any]],
    operators: list[dict[str, Any]],
    data_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create category/subcategory index artifacts for easier agent consumption."""
    root = Path(meta_dir)
    index_dir = root / "index"
    category_dir = root / "by_category"
    subcategory_dir = root / "by_subcategory"
    index_dir.mkdir(parents=True, exist_ok=True)
    category_dir.mkdir(parents=True, exist_ok=True)
    subcategory_dir.mkdir(parents=True, exist_ok=True)
    _clear_generated_artifacts(category_dir, "*.datasets.json")
    _clear_generated_artifacts(category_dir, "*.fields.json")
    _clear_generated_artifacts(subcategory_dir, "*.datasets.json")
    _clear_generated_artifacts(subcategory_dir, "*.fields.json")

    compact_datasets = [_compact_dataset(row) for row in datasets]
    dataset_lookup = {row["id"]: row for row in compact_datasets if row.get("id")}

    datasets_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    datasets_by_subcategory: dict[str, list[dict[str, Any]]] = defaultdict(list)

    category_cards: dict[str, dict[str, Any]] = {}
    subcategory_cards: dict[str, dict[str, Any]] = {}

    for row in compact_datasets:
        category = row["category"]
        subcategory = row["subcategory"]
        cat_id = category["id"]
        sub_id = subcategory["id"]

        datasets_by_category[cat_id].append(row)
        datasets_by_subcategory[sub_id].append(row)

        if cat_id not in category_cards:
            category_cards[cat_id] = {
                "id": cat_id,
                "name": category["name"],
                "meaning": _meaning_for_category(cat_id, category["name"]),
                "agent_hints": _hints_for_category(cat_id),
                "dataset_count": 0,
                "subcategory_ids": set(),
                "sample_datasets": [],
            }
        card = category_cards[cat_id]
        card["dataset_count"] += 1
        card["subcategory_ids"].add(sub_id)
        if len(card["sample_datasets"]) < 5:
            card["sample_datasets"].append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "fieldCount": row.get("fieldCount"),
                    "valueScore": row.get("valueScore"),
                }
            )

        if sub_id not in subcategory_cards:
            subcategory_cards[sub_id] = {
                "id": sub_id,
                "name": subcategory["name"],
                "category_id": cat_id,
                "category_name": category["name"],
                "meaning": f"Subdomain of {category['name']}: {subcategory['name']}",
                "dataset_count": 0,
                "sample_datasets": [],
            }
        sub_card = subcategory_cards[sub_id]
        sub_card["dataset_count"] += 1
        if len(sub_card["sample_datasets"]) < 5:
            sub_card["sample_datasets"].append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "fieldCount": row.get("fieldCount"),
                    "valueScore": row.get("valueScore"),
                }
            )

    # Serialize category and subcategory buckets.
    for cat_id, rows in datasets_by_category.items():
        write_json(category_dir / f"{_slugify(cat_id)}.datasets.json", rows)
    for sub_id, rows in datasets_by_subcategory.items():
        write_json(subcategory_dir / f"{_slugify(sub_id)}.datasets.json", rows)

    category_glossary = []
    for card in category_cards.values():
        category_glossary.append(
            {
                "id": card["id"],
                "name": card["name"],
                "meaning": card["meaning"],
                "agent_hints": card["agent_hints"],
                "dataset_count": card["dataset_count"],
                "subcategory_count": len(card["subcategory_ids"]),
                "sample_datasets": card["sample_datasets"],
            }
        )
    category_glossary.sort(key=lambda x: x["dataset_count"], reverse=True)

    subcategory_index = sorted(subcategory_cards.values(), key=lambda x: x["dataset_count"], reverse=True)

    write_json(index_dir / "category_glossary.json", category_glossary)
    write_json(index_dir / "datasets_by_category.json", category_glossary)
    write_json(index_dir / "datasets_by_subcategory.json", subcategory_index)

    operators_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in operators:
        compact = _compact_operator(row)
        operators_by_category[compact["category"]].append(compact)

    operator_index = [
        {
            "category": category,
            "operator_count": len(rows),
            "operators": rows,
        }
        for category, rows in operators_by_category.items()
    ]
    operator_index.sort(key=lambda x: x["operator_count"], reverse=True)
    write_json(index_dir / "operators_by_category.json", operator_index)

    field_count = 0
    field_categories_count = 0
    field_subcategories_count = 0
    if data_fields:
        compact_fields = [_compact_field(row, dataset_lookup) for row in data_fields]
        field_count = len(compact_fields)
        fields_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        fields_by_subcategory: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in compact_fields:
            fields_by_category[row["category"]["id"]].append(row)
            fields_by_subcategory[row["subcategory"]["id"]].append(row)
        field_categories_count = len(fields_by_category)
        field_subcategories_count = len(fields_by_subcategory)
        for cat_id, rows in fields_by_category.items():
            write_json(category_dir / f"{_slugify(cat_id)}.fields.json", rows)
        for sub_id, rows in fields_by_subcategory.items():
            write_json(subcategory_dir / f"{_slugify(sub_id)}.fields.json", rows)
        write_json(index_dir / "fields_by_category_summary.json", _field_summary(fields_by_category))
        write_json(index_dir / "fields_by_subcategory_summary.json", _field_summary(fields_by_subcategory))

    manifest = {
        "created_at": utc_now_iso(),
        "datasets": len(compact_datasets),
        "dataset_categories": len(datasets_by_category),
        "dataset_subcategories": len(datasets_by_subcategory),
        "operators": len(operators),
        "operator_categories": len(operators_by_category),
        "data_fields": field_count,
        "field_categories": field_categories_count,
        "field_subcategories": field_subcategories_count,
    }
    write_json(index_dir / "manifest.json", manifest)
    return manifest


def _compact_dataset(row: dict[str, Any]) -> dict[str, Any]:
    category = _normalize_taxon(row.get("category"), fallback_id="uncategorized", fallback_name="Uncategorized")
    subcategory = _normalize_taxon(row.get("subcategory"), fallback_id="unknown", fallback_name="Unknown")
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "description": row.get("description"),
        "category": category,
        "subcategory": subcategory,
        "coverage": row.get("coverage"),
        "dateCoverage": row.get("dateCoverage"),
        "fieldCount": row.get("fieldCount"),
        "valueScore": row.get("valueScore"),
        "alphaCount": row.get("alphaCount"),
        "userCount": row.get("userCount"),
        "themes": row.get("themes") or [],
        "region": row.get("region"),
        "delay": row.get("delay"),
        "universe": row.get("universe"),
    }


def _compact_operator(row: dict[str, Any]) -> dict[str, Any]:
    scope = row.get("scope")
    if isinstance(scope, list):
        scope_value = scope
    elif scope is None:
        scope_value = []
    else:
        scope_value = [scope]
    return {
        "name": row.get("name"),
        "category": row.get("category") or "Uncategorized",
        "scope": scope_value,
        "definition": row.get("definition"),
        "description": row.get("description"),
    }


def _compact_field(row: dict[str, Any], dataset_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    dataset_id = _dataset_id_from_field(row)
    dataset_meta = dataset_lookup.get(dataset_id, {})
    category = dataset_meta.get("category") or {"id": "uncategorized", "name": "Uncategorized"}
    subcategory = dataset_meta.get("subcategory") or {"id": "unknown", "name": "Unknown"}
    return {
        "id": row.get("id"),
        "dataset_id": dataset_id,
        "type": row.get("type"),
        "description": row.get("description"),
        "coverage": row.get("coverage"),
        "alphaCount": row.get("alphaCount"),
        "userCount": row.get("userCount"),
        "themes": row.get("themes") or [],
        "category": category,
        "subcategory": subcategory,
    }


def _field_summary(fields_by_category: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    for bucket_id, rows in fields_by_category.items():
        out.append(
            {
                "bucket_id": bucket_id,
                "field_count": len(rows),
                "dataset_count": len({row.get("dataset_id") for row in rows if row.get("dataset_id")}),
                "types": sorted({str(row.get("type")) for row in rows if row.get("type")}),
            }
        )
    out.sort(key=lambda x: x["field_count"], reverse=True)
    return out


def _normalize_taxon(value: Any, *, fallback_id: str, fallback_name: str) -> dict[str, str]:
    if isinstance(value, dict):
        tax_id = str(value.get("id") or fallback_id)
        name = str(value.get("name") or fallback_name)
        return {"id": tax_id, "name": name}
    if isinstance(value, str) and value.strip():
        text = value.strip()
        return {"id": _slugify(text), "name": text}
    return {"id": fallback_id, "name": fallback_name}


def _dataset_id_from_field(row: dict[str, Any]) -> str | None:
    dataset = row.get("dataset")
    if isinstance(dataset, dict):
        value = dataset.get("id")
        if value:
            return str(value)
    value = row.get("dataset_id")
    if value:
        return str(value)
    return None


def _meaning_for_category(category_id: str, category_name: str) -> str:
    if category_id in CATEGORY_MEANINGS:
        return CATEGORY_MEANINGS[category_id]
    lower_name = category_name.lower()
    if "model" in lower_name:
        return "Model-derived features that can be combined with base data for ranking signals."
    if "news" in lower_name:
        return "Text/news-driven informational features."
    return f"Domain-specific dataset family: {category_name}."


def _hints_for_category(category_id: str) -> dict[str, Any]:
    if category_id in CATEGORY_AGENT_HINTS:
        return CATEGORY_AGENT_HINTS[category_id]
    return {
        "signal_horizon": "unknown",
        "operator_families": ["rank", "zscore", "ts_*"],
    }


def _slugify(text: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower()).strip("-")
    return out or "unknown"


def _clear_generated_artifacts(directory: Path, pattern: str) -> None:
    for path in directory.glob(pattern):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
