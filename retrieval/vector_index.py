from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Iterable

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRecord

logger = AppLogger.get_logger()


class _EmbeddingModel:
    """Lazy Loader für SentenceTransformer."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)

        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, row)) for row in vectors]


class VectorIndex:
    """Persistenter SQLite-Vektorindex für Chunk-Embeddings."""

    def __init__(self, db_path: Path | None = None, model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = (db_path or (Path.home() / "local-knowledge-data" / "index" / "vector_index.sqlite")).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = _EmbeddingModel(model_name=model_name)

    def build(self, chunks: Iterable[ChunkRecord], rebuild: bool = False, batch_size: int = 64) -> int:
        chunk_list = list(chunks)
        logger.info("Building vector index for %s chunks", len(chunk_list))

        with sqlite3.connect(self.db_path) as connection:
            self._ensure_schema(connection)
            if rebuild:
                connection.execute("DELETE FROM chunks")

            total_written = 0
            for start in range(0, len(chunk_list), max(1, batch_size)):
                batch = chunk_list[start : start + batch_size]
                texts = [chunk.text for chunk in batch]
                vectors = self._embedder.encode(texts)

                rows = [
                    (
                        chunk.chunk_id,
                        chunk.doc_id,
                        json.dumps(vector),
                        chunk.text,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ]

                connection.executemany(
                    """
                    INSERT INTO chunks (chunk_id, doc_id, embedding, text)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        doc_id=excluded.doc_id,
                        embedding=excluded.embedding,
                        text=excluded.text
                    """,
                    rows,
                )
                total_written += len(rows)

            connection.commit()

        logger.info("Vector index build complete. written=%s db=%s", total_written, self.db_path)
        return total_written

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                embedding TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)")
