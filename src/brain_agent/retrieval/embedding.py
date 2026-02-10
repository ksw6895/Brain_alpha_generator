"""Optional embedding retriever using sentence-transformers + FAISS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EmbeddingHit:
    item_id: str
    score: float
    payload: dict[str, Any]


class EmbeddingIndex:
    """Build/search vector index for metadata retrieval.

    This module is optional by design. It requires two extra packages:
    - sentence-transformers
    - faiss-cpu (or faiss-gpu)
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None
        self._index = None
        self._rows: list[dict[str, Any]] = []
        self._id_key: str = "id"
        self._text_key: str = "text"

    def _ensure_deps(self) -> tuple[Any, Any]:
        try:
            import faiss  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Embedding retrieval requires `sentence-transformers` and `faiss` extras."
            ) from exc
        return faiss, SentenceTransformer

    def build(self, rows: list[dict[str, Any]], *, id_key: str, text_key: str) -> None:
        """Build an in-memory FAISS index from rows."""
        faiss, SentenceTransformer = self._ensure_deps()
        self._rows = rows
        self._id_key = id_key
        self._text_key = text_key

        texts = [str(row.get(text_key, "")) for row in rows]
        self._model = SentenceTransformer(self.model_name)
        vectors = self._model.encode(texts, normalize_embeddings=True)

        dim = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(vectors)

    def search(self, query: str, k: int = 20) -> list[EmbeddingHit]:
        """Search the built index."""
        if self._index is None or self._model is None:
            raise RuntimeError("Embedding index is not built")

        vec = self._model.encode([query], normalize_embeddings=True)
        scores, indices = self._index.search(vec, k)

        out: list[EmbeddingHit] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._rows):
                continue
            row = self._rows[idx]
            out.append(
                EmbeddingHit(
                    item_id=str(row.get(self._id_key, idx)),
                    score=float(score),
                    payload=row,
                )
            )
        return out
