"""Keyword/BM25 retrieval for operators, datasets, and data fields."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..storage.sqlite_store import MetadataStore

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - optional dependency
    BM25Okapi = None


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class RetrievalHit:
    item_id: str
    score: float
    payload: dict[str, Any]


class KeywordRetriever:
    """Retrieve metadata subsets relevant to idea keywords."""

    def __init__(self, store: MetadataStore) -> None:
        self.store = store

    def retrieve(self, query: str, *, op_k: int = 50, field_k: int = 50, dataset_k: int = 20) -> dict[str, list[dict[str, Any]]]:
        """Run retrieval for all metadata groups."""
        return {
            "operators": [x.payload for x in self.retrieve_operators(query, k=op_k)],
            "data_fields": [x.payload for x in self.retrieve_data_fields(query, k=field_k)],
            "datasets": [x.payload for x in self.retrieve_datasets(query, k=dataset_k)],
        }

    def retrieve_operators(self, query: str, *, k: int = 50) -> list[RetrievalHit]:
        rows = self.store.list_operators()
        return _score_rows(
            rows,
            query,
            k=k,
            id_key="name",
            text_builder=lambda r: " ".join(
                str(r.get(key, "")) for key in ("name", "category", "definition", "description", "documentation")
            ),
        )

    def retrieve_data_fields(self, query: str, *, k: int = 50) -> list[RetrievalHit]:
        rows = self.store.list_data_fields()
        return _score_rows(
            rows,
            query,
            k=k,
            id_key="id",
            text_builder=lambda r: " ".join(
                str(r.get(key, "")) for key in ("id", "dataset_id", "type", "description")
            ),
        )

    def retrieve_datasets(self, query: str, *, k: int = 20) -> list[RetrievalHit]:
        rows = self.store.list_datasets()
        return _score_rows(
            rows,
            query,
            k=k,
            id_key="id",
            text_builder=lambda r: " ".join(
                str(r.get(key, "")) for key in ("id", "name", "description", "themes")
            ),
        )


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def _idf_weighted_overlap(query_tokens: list[str], doc_tokens: list[str], corpus_df: dict[str, int], corpus_size: int) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_set = set(doc_tokens)
    score = 0.0
    for token in query_tokens:
        if token not in doc_set:
            continue
        df = corpus_df.get(token, 1)
        idf = math.log((corpus_size + 1) / (df + 1)) + 1.0
        score += idf
    return score


def _score_rows(
    rows: list[dict[str, Any]],
    query: str,
    *,
    k: int,
    id_key: str,
    text_builder: callable,
) -> list[RetrievalHit]:
    query_tokens = _tokenize(query)
    if not rows or not query_tokens:
        return []

    doc_tokens = [_tokenize(text_builder(row)) for row in rows]

    # Prefer BM25 if installed.
    if BM25Okapi is not None:
        bm25 = BM25Okapi(doc_tokens)
        scores = bm25.get_scores(query_tokens)
    else:
        df: dict[str, int] = {}
        for toks in doc_tokens:
            for token in set(toks):
                df[token] = df.get(token, 0) + 1
        scores = [_idf_weighted_overlap(query_tokens, toks, df, len(doc_tokens)) for toks in doc_tokens]

    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    out: list[RetrievalHit] = []
    for idx, score in ranked[:k]:
        if score <= 0:
            continue
        row = rows[idx]
        item_id = str(row.get(id_key) or f"row-{idx}")
        out.append(RetrievalHit(item_id=item_id, score=float(score), payload=row))
    return out
