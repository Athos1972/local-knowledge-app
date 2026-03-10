from __future__ import annotations

from dataclasses import dataclass

from sources.document import NormalizedDocument


@dataclass(slots=True)
class TextChunk:
    doc_id: str
    index: int
    text: str


class SimpleChunker:
    """Zerlegt normalisierte Texte in grobe Text-Chunks nach Zeichenlänge."""

    def __init__(self, chunk_size: int = 1000) -> None:
        self.chunk_size = chunk_size

    def chunk(self, doc: NormalizedDocument) -> list[TextChunk]:
        if not doc.content:
            return []

        chunks: list[TextChunk] = []
        start = 0
        chunk_index = 0

        while start < len(doc.content):
            end = min(start + self.chunk_size, len(doc.content))
            chunk_text = doc.content[start:end]
            chunks.append(TextChunk(doc_id=doc.doc_id, index=chunk_index, text=chunk_text))
            start = end
            chunk_index += 1

        return chunks
