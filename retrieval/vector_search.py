from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path
import sqlite3
from typing import Any

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRecord
from retrieval.keyword_search import SearchResult
from retrieval.vector_index import _EmbeddingModel

logger = AppLogger.get_logger()


@dataclass(slots=True)
class VectorChunk:
    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]


class VectorSearcher:
    """Suche über Embeddings aus dem lokalen SQLite-Index."""

    def __init__(
        self,
        db_path: Path | None = None,
        chunks: list[ChunkRecord] | None = None,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        self.db_path = (db_path or (Path.home() / "local-knowledge-data" / "index" / "vector_index.sqlite")).expanduser()
        self._embedder = _EmbeddingModel(model_name=model_name)
        self._chunk_lookup = {chunk.chunk_id: chunk for chunk in (chunks or [])}

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        vector_rows = self._load_vectors()
        if not vector_rows:
            logger.warning("No vectors found in %s. Did you run build_vector_index.py?", self.db_path)
            return []

        query_vector = self._embedder.encode([normalized_query])[0]

        scored: list[tuple[float, VectorChunk]] = []
        for row in vector_rows:
            similarity = self._cosine_similarity(query_vector, row.embedding)
            if similarity <= 0:
                continue
            scored.append((similarity, row))

        scored.sort(key=lambda item: (-item[0], item[1].doc_id, item[1].chunk_id))
        results: list[SearchResult] = []

        for score, chunk in scored[: max(1, top_k)]:
            enriched = self._chunk_lookup.get(chunk.chunk_id)
            if enriched:
                metadata: dict[str, Any] = enriched.metadata
                title = enriched.title
                source_ref = enriched.source_ref
                section_header = metadata.get("section_header") if isinstance(metadata.get("section_header"), str) else None
            else:
                metadata = {}
                title = chunk.doc_id
                source_ref = None
                section_header = None

            results.append(
                SearchResult(
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    title=title,
                    score=round(score, 4),
                    text=chunk.text,
                    metadata=metadata,
                    source_ref=source_ref,
                    section_header=section_header,
                )
            )

        logger.info("Vector search completed. query=%s hits=%s", normalized_query, len(results))
        return results

    def _load_vectors(self) -> list[VectorChunk]:
        if not self.db_path.exists():
            return []

        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute("SELECT chunk_id, doc_id, embedding, text FROM chunks").fetchall()

        vectors: list[VectorChunk] = []
        for chunk_id, doc_id, embedding_json, text in rows:
            try:
                embedding = json.loads(embedding_json)
            except json.JSONDecodeError:
                continue

            if not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding):
                continue

            vectors.append(
                VectorChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    embedding=[float(value) for value in embedding],
                )
            )

        return vectors

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0

        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = sqrt(sum(a * a for a in left))
        right_norm = sqrt(sum(b * b for b in right))

        if left_norm == 0 or right_norm == 0:
            return 0.0

        return dot / (left_norm * right_norm)
