from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from common.logging_setup import AppLogger
from retrieval.chunk_repository import ChunkRecord
from retrieval.embedding_provider import EmbeddingProvider

logger = AppLogger.get_logger()


class VectorIndex:
    """Persistenter SQLite-Vektorindex für Chunk-Embeddings."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        db_path: Path | None = None,
    ):
        self.db_path = (db_path or (Path.home() / "local-knowledge-data" / "index" / "vector_index.sqlite")).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider

    def build(self, chunks: Iterable[ChunkRecord], rebuild: bool = False, batch_size: int = 64) -> int:
        chunk_list = list(chunks)
        logger.info(
            "Building vector index chunks=%s provider=%s model=%s",
            len(chunk_list),
            self.embedding_provider.provider_name,
            self.embedding_provider.model_name,
        )

        with sqlite3.connect(self.db_path) as connection:
            self._ensure_schema(connection)
            existing_meta = self.read_metadata(connection)
            if existing_meta and not rebuild:
                self._validate_index_compatibility(existing_meta)

            if rebuild:
                connection.execute("DELETE FROM chunks")

            total_written = 0
            detected_dimension: int | None = None

            for start in range(0, len(chunk_list), max(1, batch_size)):
                batch = chunk_list[start : start + batch_size]
                texts = [chunk.text for chunk in batch]
                vectors = self.embedding_provider.embed_texts(texts)
                if vectors and detected_dimension is None:
                    detected_dimension = len(vectors[0])

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

            self._write_metadata(connection, embedding_dimension=detected_dimension)
            connection.commit()

        logger.info("Vector index build complete. written=%s db=%s", total_written, self.db_path)
        return total_written

    def get_metadata(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as connection:
            self._ensure_schema(connection)
            return self.read_metadata(connection)

    def read_metadata(self, connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute("SELECT key, value FROM metadata").fetchall()
        return {str(key): str(value) for key, value in rows}

    def _write_metadata(self, connection: sqlite3.Connection, embedding_dimension: int | None) -> None:
        metadata = {
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model": self.embedding_provider.model_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if embedding_dimension is not None:
            metadata["embedding_dimension"] = str(embedding_dimension)

        connection.executemany(
            """
            INSERT INTO metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            list(metadata.items()),
        )

    def _validate_index_compatibility(self, existing_meta: dict[str, str]) -> None:
        index_model = existing_meta.get("embedding_model")
        index_provider = existing_meta.get("embedding_provider")
        if index_model and index_model != self.embedding_provider.model_name:
            raise ValueError(
                "Der Vektorindex wurde mit Modell "
                f"{index_model} erstellt, die Anfrage verwendet aber Modell {self.embedding_provider.model_name}. "
                "Bitte Index neu bauen."
            )
        if index_provider and index_provider != self.embedding_provider.provider_name:
            raise ValueError(
                "Der Vektorindex wurde mit Provider "
                f"{index_provider} erstellt, die Anfrage verwendet aber Provider {self.embedding_provider.provider_name}. "
                "Bitte Index neu bauen."
            )

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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
