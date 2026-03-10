"""Markdown-aware Chunking entlang von Überschriften mit robustem Fallback.

Dieser Chunker erkennt Markdown-Header (`#` bis `######`) als Section-Grenzen,
führt kleine Sections zusammen und splittet zu große Sections deterministisch
zeichenbasiert. Wenn keine Header vorhanden sind, wird automatisch auf den
bestehenden `SimpleChunker` zurückgegriffen.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from common.logging_setup import AppLogger
from processing.simple_chunker import SimpleChunker
from sources.document import ChunkDocument, NormalizedDocument, stable_hash

logger = AppLogger.get_logger()

_HEADER_RE = re.compile(r"^#{1,6}\s+")


@dataclass(slots=True)
class Section:
    """Interne, pragmatische Repräsentation einer Markdown-Section."""

    header: str
    level: int
    content: str

    def render_text(self) -> str:
        """Rendert Header + Content in einen stabilen Section-Text."""
        if self.level > 0:
            header_line = f"{'#' * self.level} {self.header}".strip()
            if self.content.strip():
                return f"{header_line}\n{self.content.strip()}"
            return header_line
        return self.content.strip()


class MarkdownChunker:
    """Erzeugt Chunks entlang von Markdown-Sections mit deterministischem Fallback."""

    def __init__(self, max_chunk_size: int = 1200, min_chunk_size: int = 200, overlap: int = 100):
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be > 0")
        if min_chunk_size < 0:
            raise ValueError("min_chunk_size must be >= 0")
        if min_chunk_size > max_chunk_size:
            raise ValueError("min_chunk_size must be <= max_chunk_size")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= max_chunk_size:
            raise ValueError("overlap must be smaller than max_chunk_size")

        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap
        self._fallback_chunker = SimpleChunker(chunk_size=max_chunk_size, overlap=overlap)

    def chunk_document(self, doc: NormalizedDocument) -> list[ChunkDocument]:
        """Chunkt ein Dokument section-aware; ohne Header via SimpleChunker."""
        text = doc.body.strip()
        if not text:
            logger.debug("Skipping markdown chunking for empty body. doc_id=%s", doc.doc_id)
            return []

        sections = self._parse_sections(text)
        if not sections:
            fallback_chunks = self._fallback_chunker.chunk_document(doc)
            logger.debug(
                "No markdown headers detected. Used fallback chunker. doc_id=%s chunks=%s",
                doc.doc_id,
                len(fallback_chunks),
            )
            return fallback_chunks

        merged_sections = self._merge_small_sections(sections)

        chunks: list[ChunkDocument] = []
        for section in merged_sections:
            section_text = section.render_text()
            if len(section_text) <= self.max_chunk_size:
                chunks.append(
                    self._build_chunk(
                        doc=doc,
                        chunk_index=len(chunks),
                        text=section_text,
                        section_header=section.header,
                        section_level=section.level,
                    )
                )
                continue

            chunks.extend(self._split_large_section(doc, section, start_index=len(chunks)))

        logger.debug(
            "Markdown chunking completed. doc_id=%s sections=%s chunks=%s",
            doc.doc_id,
            len(merged_sections),
            len(chunks),
        )
        return chunks

    def _parse_sections(self, text: str) -> list[Section]:
        """Parst Markdown-Header und baut daraus Sections."""
        sections: list[Section] = []
        current_header = ""
        current_level = 0
        current_content: list[str] = []
        found_header = False

        for line in text.splitlines():
            if _HEADER_RE.match(line):
                found_header = True
                self._append_section(sections, current_header, current_level, current_content)

                level = len(line) - len(line.lstrip("#"))
                current_level = max(1, min(level, 6))
                current_header = line[current_level:].strip()
                current_content = []
                continue

            current_content.append(line)

        self._append_section(sections, current_header, current_level, current_content)

        if not found_header:
            return []
        return sections

    def _merge_small_sections(self, sections: list[Section]) -> list[Section]:
        """Führt kleine Sections mit der vorherigen zusammen."""
        merged: list[Section] = []

        for section in sections:
            section_text = section.render_text()
            if len(section_text) < self.min_chunk_size and merged:
                previous = merged[-1]
                merged_content = self._join_content(previous.content, section.render_text())
                merged[-1] = Section(
                    header=previous.header,
                    level=previous.level,
                    content=merged_content,
                )
                continue

            merged.append(section)

        return merged

    def _split_large_section(
        self,
        doc: NormalizedDocument,
        section: Section,
        start_index: int,
    ) -> list[ChunkDocument]:
        """Splittet eine große Section deterministisch zeichenbasiert mit Overlap."""
        section_text = section.render_text()
        step = self.max_chunk_size - self.overlap
        chunks: list[ChunkDocument] = []

        for local_index, start in enumerate(range(0, len(section_text), step)):
            raw_chunk = section_text[start : start + self.max_chunk_size]
            chunk_text = raw_chunk.strip()
            if not chunk_text:
                continue

            chunks.append(
                self._build_chunk(
                    doc=doc,
                    chunk_index=start_index + local_index,
                    text=chunk_text,
                    section_header=section.header,
                    section_level=section.level,
                )
            )

            if start + self.max_chunk_size >= len(section_text):
                break

        return chunks

    def _build_chunk(
        self,
        doc: NormalizedDocument,
        chunk_index: int,
        text: str,
        section_header: str,
        section_level: int,
    ) -> ChunkDocument:
        """Erzeugt ein ChunkDocument mit standardisierten Metadaten."""
        chunk_id = f"{doc.doc_id}-chunk-{chunk_index:04d}"
        return ChunkDocument(
            chunk_id=chunk_id,
            doc_id=doc.doc_id,
            chunk_index=chunk_index,
            text=text,
            title=doc.title,
            doc_type=doc.doc_type,
            source_type=doc.source.source_type,
            source_name=doc.source.source_name,
            metadata={
                "section_header": section_header,
                "section_level": section_level,
                "document_checksum": doc.checksum,
                "tags": doc.tags,
            },
            checksum=stable_hash(text),
        )

    @staticmethod
    def _append_section(
        sections: list[Section],
        header: str,
        level: int,
        content_lines: list[str],
    ) -> None:
        """Hängt eine nicht-leere Section an die Sectionliste an."""
        content = "\n".join(content_lines).strip()
        if not header and not content:
            return
        sections.append(Section(header=header, level=level, content=content))

    @staticmethod
    def _join_content(base: str, addition: str) -> str:
        """Verbindet zwei Textteile mit genau einer Leerzeile."""
        left = base.strip()
        right = addition.strip()
        if not left:
            return right
        if not right:
            return left
        return f"{left}\n\n{right}"
