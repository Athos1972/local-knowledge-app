from __future__ import annotations

"""Streamlit UI for the local-first knowledge assistant."""

import os
from typing import Any

import streamlit as st

from engine import LocalFirstRAGEngine, SourceChunk


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@st.cache_resource(show_spinner=False)
def load_engine(
    data_dir: str,
    vector_backend: str,
    llm_model: str,
    embedding_model: str,
    similarity_top_k: int,
) -> LocalFirstRAGEngine:
    """Cache engine instances for faster Streamlit reruns."""
    return LocalFirstRAGEngine(
        data_dir=data_dir,
        vector_backend=vector_backend,
        llm_model=llm_model,
        embedding_model=embedding_model,
        similarity_top_k=similarity_top_k,
        rerank_top_n=7,
    )


def build_source_filters(
    jira_enabled: bool,
    confluence_enabled: bool,
    web_enabled: bool,
) -> list[str]:
    """Map sidebar checkboxes to engine metadata filters."""
    source_filters: list[str] = []
    if jira_enabled:
        source_filters.append("jira")
    if confluence_enabled:
        source_filters.append("confluence")
    if web_enabled:
        source_filters.append("web")
    return source_filters


def render_sources(sources: list[dict[str, Any]]) -> None:
    """Render source links under each assistant answer."""
    if not sources:
        st.caption("Keine Quellen gefunden.")
        return

    with st.expander("Quellen anzeigen"):
        for idx, source in enumerate(sources, start=1):
            metadata = source.get("metadata", {})
            source_name = metadata.get("source", "unknown")
            source_link = metadata.get("source_link") or metadata.get("path")
            score = source.get("score", 0.0)
            st.markdown(f"{idx}. **{source_name}** – {source_link} _(score={score:.3f})_")


def serialize_sources(sources: list[SourceChunk]) -> list[dict[str, Any]]:
    """Convert typed engine output into Streamlit session-compatible payload."""
    return [{"score": chunk.score, "metadata": chunk.metadata} for chunk in sources]


st.set_page_config(page_title="Local-First Knowledge App", page_icon="🧠", layout="wide")
st.title("🧠 Local-First Knowledge App")
st.caption("Hybrid Search (BM25 + Vektor) mit Reranking (BAAI/bge-reranker-v2-m3)")

with st.sidebar:
    st.header("Einstellungen")
    llm_model = st.selectbox("Ollama Modell", options=["llama3:70b", "llama3:8b"], index=0)
    vector_backend = st.selectbox("Vector Store", options=["qdrant", "chroma"], index=0)

    st.subheader("Quellen-Filter")
    jira_enabled = st.checkbox("Jira", value=True)
    confluence_enabled = st.checkbox("Confluence", value=True)
    web_enabled = st.checkbox("Web", value=True)

    similarity_top_k = st.slider(
        "Similarity Top-K (vor Reranking)",
        min_value=20,
        max_value=200,
        value=100,
        step=10,
    )

source_filters = build_source_filters(jira_enabled, confluence_enabled, web_enabled)

if "messages" not in st.session_state:
    st.session_state.messages = []

try:
    engine = load_engine(
        data_dir=_env("LKA_DATA_DIR", "./data"),
        vector_backend=vector_backend,
        llm_model=llm_model,
        embedding_model=_env("LKA_EMBEDDING_MODEL", "nomic-embed-text"),
        similarity_top_k=similarity_top_k,
    )
except Exception as exc:
    st.error(f"Engine konnte nicht initialisiert werden: {exc}")
    st.stop()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(message.get("sources", []))

if prompt := st.chat_input("Frage zur Wissensbasis..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Suche und antworte..."):
            answer, source_chunks = engine.query(
                prompt,
                source_filters=source_filters,
                similarity_top_k=similarity_top_k,
            )

        st.markdown(answer)
        source_payload = serialize_sources(source_chunks)
        render_sources(source_payload)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": source_payload}
    )
