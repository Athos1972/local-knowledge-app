#!/usr/bin/env python3
"""Erzeugt/aktualisiert den lokalen Vector-Index aus Chunk-JSONL-Dateien."""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import AppLogger
from processing.audit import AuditStage, ReasonCode, build_audit_components
from retrieval.chunk_repository import ChunkRepository
from retrieval.embedding_provider import EmbeddingProviderError
from retrieval.embedding_provider import build_embedding_provider
from retrieval.runtime_settings import RuntimeSettings
from retrieval.vector_index import VectorIndex


def parse_args() -> argparse.Namespace:
    settings = RuntimeSettings.load()

    parser = argparse.ArgumentParser(description="Build vector index from local chunks")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "local-knowledge-data",
        help="Daten-Root mit processed/chunks und index/",
    )
    parser.add_argument("--rebuild", action="store_true", help="Bestehenden Index vor Neuaufbau leeren")
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "sentence_transformers"],
        default=settings.embedding_provider,
        help="Embedding-Provider (Standard aus Konfiguration)",
    )
    parser.add_argument(
        "--embedding-model",
        default=settings.ollama_embed_model,
        help="Embedding-Modellname (Standard aus Konfiguration)",
    )
    parser.add_argument(
        "--ollama-url",
        default=settings.ollama_base_url,
        help="Ollama Base URL für Embeddings",
    )
    parser.add_argument("--run-id", default=None, help="Optionale Run-ID für Audit-Korrelation")
    parser.add_argument("--source-instance", default="local-index")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = AppLogger.get_logger()
    started = perf_counter()
    mode = "rebuild" if args.rebuild else "incremental"
    run_context, audit = build_audit_components(
        data_root=args.root,
        source_type="filesystem",
        source_instance=args.source_instance,
        mode=mode,
        run_id=args.run_id,
    )

    repository = ChunkRepository(data_root=args.root)
    with audit.stage(
        run_id=run_context.run_id,
        source_type="filesystem",
        source_instance=args.source_instance,
        stage=AuditStage.LOAD,
        document_id="__all_chunks__",
        document_title="all chunks",
    ) as load_evt:
        chunks = repository.load_chunks()
        load_evt.event.output_count = len(chunks)
    logger.info("Loaded chunks for vector index build: %s", len(chunks))

    if not chunks:
        run_context.finish(status="finished_with_errors")
        print("Keine Chunks gefunden. Bitte zuerst Ingestion ausführen.")
        return 1

    index_path = args.root.expanduser().resolve() / "index" / "vector_index.sqlite"

    try:
        embedding_provider = build_embedding_provider(
            provider_name=args.embedding_provider,
            model_name=args.embedding_model,
            ollama_base_url=args.ollama_url,
        )
        index = VectorIndex(db_path=index_path, embedding_provider=embedding_provider)
        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.EMBED,
            document_id="__all_chunks__",
            document_title="all chunks",
        ) as embed_evt:
            embed_evt.event.input_count = len(chunks)
            written = index.build(chunks, rebuild=args.rebuild)
            embed_evt.event.output_count = written

        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.INDEX,
            document_id="__all_chunks__",
            document_title="vector index",
        ) as index_evt:
            index_evt.event.input_count = len(chunks)
            index_evt.event.output_count = written
    except EmbeddingProviderError as error:
        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.EMBED,
            document_id="__all_chunks__",
            document_title="all chunks",
        ) as embed_error_evt:
            embed_error_evt.error(ReasonCode.EMBED_EXCEPTION, str(error))
        run_context.finish(status="finished_with_errors")
        logger.error("Embedding provider error: %s", error)
        print(f"Fehler beim Embedding-Provider ({args.embedding_provider}/{args.embedding_model}): {error}")
        return 2
    except ValueError as error:
        with audit.stage(
            run_id=run_context.run_id,
            source_type="filesystem",
            source_instance=args.source_instance,
            stage=AuditStage.INDEX,
            document_id="__all_chunks__",
            document_title="vector index",
        ) as index_error_evt:
            index_error_evt.error(ReasonCode.INDEX_WRITE_EXCEPTION, str(error))
        run_context.finish(status="finished_with_errors")
        logger.error("Index compatibility error: %s", error)
        print(str(error))
        return 2

    runtime_seconds = perf_counter() - started
    metadata = index.get_metadata()

    print(f"Vector index erfolgreich erstellt/aktualisiert: {index_path}")
    print(f"Gespeicherte Chunks: {written}")
    print(f"Embedding Provider: {metadata.get('embedding_provider', args.embedding_provider)}")
    print(f"Embedding Modell: {metadata.get('embedding_model', args.embedding_model)}")
    if metadata.get("embedding_dimension"):
        print(f"Embedding Dimension: {metadata['embedding_dimension']}")
    print(f"Laufzeit: {runtime_seconds:.2f}s")

    logger.info(
        "Vector index build done path=%s chunks=%s provider=%s embedding_model=%s runtime_seconds=%.2f",
        index_path,
        written,
        metadata.get("embedding_provider", args.embedding_provider),
        metadata.get("embedding_model", args.embedding_model),
        runtime_seconds,
    )
    run_context.finish(status="finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
