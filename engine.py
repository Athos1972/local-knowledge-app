from __future__ import annotations

"""LlamaIndex-backed local-first retrieval engine.

This module encapsulates ingestion, index construction, hybrid retrieval
(BM25 + vector), metadata filtering and reranking.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.retrievers import BM25Retriever, QueryFusionRetriever, VectorIndexRetriever
from llama_index.core.schema import BaseNode, NodeWithScore
from llama_index.core.vector_stores.types import (
    ExactMatchFilter,
    FilterCondition,
    MetadataFilters,
)
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.vector_stores.qdrant import QdrantVectorStore

from ingestion import MarkdownIngestor


@dataclass(frozen=True)
class SourceChunk:
    """Serializable result chunk returned to the UI layer."""

    text: str
    score: float
    metadata: dict[str, Any]


class LocalFirstRAGEngine:
    """RAG engine optimized for local corpora and local model serving.

    Features:
    - VectorStoreIndex with Qdrant (default) or Chroma
    - Hybrid retrieval via vector + BM25 fusion
    - SentenceTransformer reranking (top_k -> top_n)
    - Metadata filters for source-limited retrieval
    """

    def __init__(
        self,
        data_dir: str,
        vector_backend: str = "qdrant",
        qdrant_path: str = "./qdrant_data",
        chroma_path: str = "./chroma_data",
        collection_name: str = "knowledge_base",
        ollama_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3:70b",
        embedding_model: str = "nomic-embed-text",
        rerank_model: str = "BAAI/bge-reranker-v2-m3",
        rerank_top_n: int = 7,
        similarity_top_k: int = 100,
    ):
        self.data_dir = Path(data_dir)
        self.vector_backend = vector_backend.lower().strip()
        self.qdrant_path = Path(qdrant_path)
        self.chroma_path = Path(chroma_path)
        self.collection_name = collection_name
        self.ollama_base_url = ollama_base_url
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
        self.rerank_top_n = rerank_top_n
        self.similarity_top_k = similarity_top_k

        self._configure_global_settings()
        self.index, self.nodes = self._build_index()

    def _configure_global_settings(self) -> None:
        """Configure global LlamaIndex models and Apple Silicon fallback."""
        Settings.llm = Ollama(
            model=self.llm_model,
            base_url=self.ollama_base_url,
            request_timeout=120.0,
        )
        Settings.embed_model = OllamaEmbedding(
            model_name=self.embedding_model,
            base_url=self.ollama_base_url,
        )

        # Apple Silicon optimization: use MPS and allow CPU fallback.
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    def _build_storage_context(self) -> StorageContext:
        """Create the configured vector store backend."""
        if self.vector_backend == "qdrant":
            import qdrant_client

            self.qdrant_path.mkdir(parents=True, exist_ok=True)
            qdrant_client_local = qdrant_client.QdrantClient(path=str(self.qdrant_path))
            vector_store = QdrantVectorStore(
                client=qdrant_client_local,
                collection_name=self.collection_name,
                enable_hybrid=True,
            )
        elif self.vector_backend == "chroma":
            import chromadb

            self.chroma_path.mkdir(parents=True, exist_ok=True)
            chroma_client = chromadb.PersistentClient(path=str(self.chroma_path))
            chroma_collection = chroma_client.get_or_create_collection(name=self.collection_name)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        else:
            raise ValueError("vector_backend must be one of: qdrant, chroma")

        return StorageContext.from_defaults(vector_store=vector_store)

    def _build_index(self) -> tuple[VectorStoreIndex, list[BaseNode]]:
        """Load markdown data and build/update the vector index."""
        storage_context = self._build_storage_context()
        ingestor = MarkdownIngestor(self.data_dir)
        documents, stats = ingestor.load_documents()

        if not documents:
            raise ValueError(f"No markdown documents found in {self.data_dir}")

        # For large corpora, this path can be switched to incremental ingestion.
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True,
        )
        nodes = list(index.docstore.docs.values())

        print(
            f"[engine] indexed documents={stats.documents_loaded} "
            f"(scanned={stats.files_scanned}) backend={self.vector_backend}"
        )
        return index, nodes

    def query(
        self,
        question: str,
        source_filters: list[str] | None = None,
        similarity_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk]]:
        """Run hybrid retrieval + rerank + LLM answer generation."""
        similarity_top_k = similarity_top_k or self.similarity_top_k
        metadata_filters = self._build_metadata_filters(source_filters)

        vector_retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=similarity_top_k,
            filters=metadata_filters,
            vector_store_query_mode="hybrid",
        )

        bm25_nodes = self._filter_nodes_for_sources(source_filters)
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=bm25_nodes,
            similarity_top_k=similarity_top_k,
        )

        fusion_retriever = QueryFusionRetriever(
            retrievers=[vector_retriever, bm25_retriever],
            similarity_top_k=similarity_top_k,
            mode="relative_score",
            num_queries=1,
            use_async=False,
        )

        reranker_device = self._select_reranker_device()
        reranker = SentenceTransformerRerank(
            model=self.rerank_model,
            top_n=self.rerank_top_n,
            device=reranker_device,
        )

        retrieved_nodes = fusion_retriever.retrieve(question)
        reranked_nodes = reranker.postprocess_nodes(retrieved_nodes, query_str=question)

        context = "\n\n".join(node.get_content() for node in reranked_nodes)
        prompt = (
            "Du bist ein präziser Assistent für Unternehmenswissen. "
            "Nutze nur den gegebenen Kontext. Wenn Informationen fehlen, sage das klar.\n\n"
            f"Frage: {question}\n\nKontext:\n{context}"
        )

        llm_response = Settings.llm.complete(prompt)
        sources = [self._to_source_chunk(node) for node in reranked_nodes]
        return str(llm_response), sources

    @staticmethod
    def _build_metadata_filters(source_filters: list[str] | None) -> MetadataFilters | None:
        """Build OR filters so Jira/Confluence/Web checkboxes behave intuitively."""
        if not source_filters:
            return None

        return MetadataFilters(
            filters=[ExactMatchFilter(key="source", value=source) for source in source_filters],
            condition=FilterCondition.OR,
        )

    def _filter_nodes_for_sources(self, source_filters: list[str] | None) -> list[BaseNode]:
        """Apply source filters to BM25 candidate set."""
        if not source_filters:
            return self.nodes

        allowed = {source.lower() for source in source_filters}
        return [
            node
            for node in self.nodes
            if str(node.metadata.get("source", "")).lower() in allowed
        ]

    @staticmethod
    def _select_reranker_device() -> str:
        """Select device for reranker with Apple Silicon preference."""
        import importlib.util

        if importlib.util.find_spec("torch") is None:
            return "cpu"

        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    @staticmethod
    def _to_source_chunk(node: NodeWithScore) -> SourceChunk:
        metadata = node.metadata or {}
        return SourceChunk(
            text=node.get_content(),
            score=float(node.score or 0.0),
            metadata=metadata,
        )
