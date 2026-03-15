"""Haupttransformer für Confluence-Rohseiten."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from time import perf_counter

from processing.confluence.link_transformer import LinkTransformer
from processing.confluence.macro_transformer import MacroTransformer
from processing.confluence.models import ConfluenceRawPage, ConfluenceTransformedPage, TransformWarning
from processing.confluence.page_properties import (
    build_frontmatter_promoted_properties,
    load_property_promotion_rules,
)
from processing.confluence.table_transformer import TableTransformer
from processing.confluence.writer import ConfluenceTransformWriter
from processing.image_analysis.models import DerivedFileArtifact, ParentDocumentContext
from sources.document import stable_hash
from processing.terminology import TerminologyService
from transformers.router import TransformRouter


_IGNORE_TITLE_PATTERN = re.compile(r"^log\s+\d{4}\b", flags=re.IGNORECASE)


logger = logging.getLogger(__name__)


class ConfluenceTransformer:
    """Transformiert Rohseiten in ingestierbares Markdown."""

    def __init__(self) -> None:
        self.macro_transformer = MacroTransformer()
        self.property_promotion_rules = load_property_promotion_rules()
        self.table_transformer = TableTransformer(self.property_promotion_rules)
        self.link_transformer = LinkTransformer()
        self.terminology_service = TerminologyService()
        self.transform_router = TransformRouter()

    def finalize_terminology_report(self) -> Path | None:
        """Finalize and write the aggregated terminology candidate report."""
        return self.terminology_service.finalize_candidate_report()

    def should_ignore_page(self, page: ConfluenceRawPage) -> bool:
        """Prüft, ob eine Seite anhand ihres Titels aus der Verarbeitung ausgeschlossen wird."""
        return self.should_ignore_title(page.title)

    def should_ignore_title(self, title: str) -> bool:
        """Ignoriert Log-Seiten mit Titelpräfix `Log YYYY` (case-insensitiv)."""
        return bool(_IGNORE_TITLE_PATTERN.match(title.strip()))

    def transform(self, page: ConfluenceRawPage) -> ConfluenceTransformedPage:
        warnings: list[TransformWarning] = []

        attachment_signature = ",".join(
            sorted(
                f"{item.get('name','')}|{item.get('local_path','')}"
                for item in page.attachments
                if isinstance(item, dict)
            )
        )
        source_content_hash = stable_hash(
            "|".join([page.title, page.body, page.updated_at or "", ",".join(page.labels), attachment_signature])
        )

        text = page.body
        text, macro_warnings, unsupported = self.macro_transformer.transform(text)
        warnings.extend(macro_warnings)

        page_slug = ConfluenceTransformWriter._slugify(page.title)
        text, extracted_properties, key_value_count, extra_documents = self.table_transformer.transform(
            text,
            page_id=page.page_id,
            space_key=page.space_key,
            page_title=page.title,
            page_slug=page_slug,
            source_url=page.source_url,
            labels=page.labels,
            parent_title=page.parent_title,
            content_hash=source_content_hash,
            warnings=warnings,
        )
        merged_page_properties = self._merge_page_properties(page.page_properties, extracted_properties)
        promoted_properties = build_frontmatter_promoted_properties(merged_page_properties, self.property_promotion_rules)

        if key_value_count:
            logger.debug("Seite %s: %s Key-Value-Tabellen erkannt.", page.page_id, key_value_count)

        text = self.link_transformer.transform(text, source_url=page.source_url)
        text = self._convert_structure(text)
        text = self._remove_empty_headings(text)
        text = self._cleanup_whitespace(text)

        task_metadata = self._extract_task_metadata(text)
        promoted_properties.update(task_metadata)

        title_prefix = f"# {page.title}\n\n"
        body = title_prefix + text.strip()
        attachment_sections, image_analysis_refs, derived_artifacts = self._render_attachment_content(page, warnings)
        attachment_stats = self._build_attachment_stats(page, warnings)
        if attachment_sections:
            body += "\n\n## Anhang-Inhalte (extrahiert)\n\n" + "\n".join(attachment_sections).strip()
        if image_analysis_refs:
            links = [
                f"- [{item.get('attachment_name', 'Bildanalyse')}]({item.get('derived_md_file', '')})"
                for item in image_analysis_refs
                if item.get("derived_md_file")
            ]
            if links:
                body += "\n\n## Abgeleitete Bildanalysen\n\n" + "\n".join(links)
        body += self.link_transformer.render_attachments(page.attachments)

        terminology_result = self.terminology_service.apply_to_text(
            body,
            source_type="confluence",
            source_ref=page.source_ref,
        )

        return ConfluenceTransformedPage(
            page_id=page.page_id,
            space_key=page.space_key,
            title=page.title,
            body_markdown=terminology_result.text,
            source_ref=page.source_ref,
            source_url=page.source_url,
            created_at=page.created_at,
            updated_at=page.updated_at,
            author=page.author,
            labels=page.labels,
            parent_title=page.parent_title,
            ancestors=page.ancestors,
            page_properties=merged_page_properties,
            promoted_properties=promoted_properties,
            attachments=page.attachments,
            transform_warnings=warnings,
            attachment_stats=attachment_stats,
            unsupported_macros=unsupported,
            extra_documents=extra_documents,
            image_analysis_refs=image_analysis_refs,
            derived_artifacts=derived_artifacts,
            content_hash=source_content_hash,
        )

    def _render_attachment_content(
        self,
        page: ConfluenceRawPage,
        warnings: list[TransformWarning],
    ) -> tuple[list[str], list[dict[str, object]], list[DerivedFileArtifact]]:
        sections: list[str] = []
        image_analysis_refs: list[dict[str, object]] = []
        derived_artifacts: list[DerivedFileArtifact] = []
        indexed = {Path(path).name: path for path in page.attachment_paths}
        attachment_timings: dict[str, float] = {}

        for attachment in page.attachments:
            if not isinstance(attachment, dict):
                continue

            name = str(attachment.get("name") or attachment.get("title") or attachment.get("filename") or "Anhang")
            suffix = self._attachment_suffix(name=name, local_path=attachment.get("local_path"))
            local_path_raw = attachment.get("local_path")
            if isinstance(local_path_raw, str) and local_path_raw.strip():
                path = Path(local_path_raw.strip()).expanduser()
            elif name in indexed:
                path = Path(indexed[name])
                attachment.setdefault("local_path", str(path))
            else:
                warnings.append(
                    TransformWarning(
                        code="attachment_missing_local_path",
                        message=f"Anhang '{name}' hat keinen auflösbaren lokalen Pfad.",
                        context=name,
                    )
                )
                continue

            if not path.exists() or not path.is_file():
                warnings.append(
                    TransformWarning(
                        code="attachment_file_not_found",
                        message=f"Anhang-Datei nicht gefunden: {path}",
                        context=name,
                    )
                )
                continue

            transformer = self.transform_router.resolve(path)
            if transformer is None:
                warnings.append(
                    TransformWarning(
                        code="attachment_unsupported_extension",
                        message=f"Anhang '{name}' hat nicht unterstützte Endung '{path.suffix.lower()}'.",
                        context=name,
                    )
                )
                continue

            started = perf_counter()
            context = ParentDocumentContext(
                source_system="confluence",
                parent_id=page.page_id,
                parent_title=page.title,
                parent_source_ref=page.source_ref,
                parent_source_url=page.source_url,
                parent_output_name=f"{page.page_id}__{ConfluenceTransformWriter._slugify(page.title)}.md",
                section_hint="attachments",
                surrounding_text=page.body,
            )
            result = transformer.transform(path, context=context)
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            attachment_timings[f"{name}|{suffix}"] = elapsed_ms
            if not result.success:
                warnings.append(
                    TransformWarning(
                        code="attachment_transform_failed",
                        message=f"Anhang '{name}' konnte nicht transformiert werden: {result.error or 'unbekannter Fehler'}",
                        context=name,
                    )
                )
                continue

            markdown = result.markdown.strip()
            if not markdown:
                warnings.append(
                    TransformWarning(
                        code="attachment_empty_markdown",
                        message=f"Anhang '{name}' lieferte leeres Markdown.",
                        context=name,
                    )
                )
                continue

            for warn in result.warnings:
                warnings.append(
                    TransformWarning(
                        code="attachment_transform_warning",
                        message=f"Anhang '{name}': {warn}",
                        context=name,
                    )
                )

            if elapsed_ms >= 1000:
                logger.info(
                    "Confluence attachment transformed. page_id=%s attachment=%s suffix=%s duration_ms=%.2f",
                    page.page_id,
                    name,
                    suffix,
                    elapsed_ms,
                )

            image_ref = result.metadata.get("image_analysis_ref")
            if isinstance(image_ref, dict):
                image_analysis_refs.append(image_ref)
            artifacts = result.metadata.get("derived_artifacts")
            if isinstance(artifacts, list):
                for artifact in artifacts:
                    if not isinstance(artifact, dict):
                        continue
                    file_name = artifact.get("file_name")
                    media_type = artifact.get("media_type")
                    content = artifact.get("content")
                    if isinstance(file_name, str) and isinstance(media_type, str) and isinstance(content, str):
                        derived_artifacts.append(
                            DerivedFileArtifact(file_name=file_name, media_type=media_type, content=content)
                        )

            sections.extend([f"### {name}", "", markdown, ""])

        if attachment_timings:
            page.raw_metadata["_attachment_timings_ms"] = attachment_timings
        return sections, image_analysis_refs, derived_artifacts

    def _build_attachment_stats(self, page: ConfluenceRawPage, warnings: list[TransformWarning]) -> dict[str, object]:
        suffix_counts: dict[str, int] = {}
        duration_by_suffix_ms: dict[str, float] = {}
        extracted = 0
        raw_timings = page.raw_metadata.get("_attachment_timings_ms", {})
        if isinstance(raw_timings, dict):
            for key, elapsed_ms in raw_timings.items():
                _name, _sep, suffix = str(key).rpartition("|")
                suffix = suffix or "<noext>"
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                duration_by_suffix_ms[suffix] = duration_by_suffix_ms.get(suffix, 0.0) + float(elapsed_ms)
                extracted += 1

        warning_counts: dict[str, int] = {}
        warning_suffixes: dict[str, int] = {}
        for warning in warnings:
            if not warning.code.startswith("attachment_"):
                continue
            warning_counts[warning.code] = warning_counts.get(warning.code, 0) + 1
            suffix = self._attachment_suffix(name=warning.context or "")
            warning_suffixes[suffix] = warning_suffixes.get(suffix, 0) + 1

        return {
            "total": len(page.attachments),
            "extracted": extracted,
            "failed": sum(warning_counts.values()),
            "suffix_counts": suffix_counts,
            "duration_by_suffix_ms": {key: round(value, 2) for key, value in duration_by_suffix_ms.items()},
            "warning_counts": warning_counts,
            "warning_suffixes": warning_suffixes,
        }

    @staticmethod
    def _attachment_suffix(*, name: str, local_path: object | None = None) -> str:
        if isinstance(local_path, str) and local_path.strip():
            suffix = Path(local_path.strip()).suffix.lower()
            return suffix or "<noext>"
        suffix = Path(name).suffix.lower()
        return suffix or "<noext>"

    def _merge_page_properties(self, existing: dict[str, object], extracted: dict[str, str]) -> dict[str, object]:
        """Ergänzt erkannte Seiteneigenschaften ohne vorhandene Werte zu überschreiben."""
        merged: dict[str, object] = dict(existing)
        for key, value in extracted.items():
            if key not in merged:
                merged[key] = value
        return merged

    def _convert_structure(self, text: str) -> str:
        conversions = [
            (r"<h1[^>]*>(.*?)</h1>", r"# \1\n"),
            (r"<h2[^>]*>(.*?)</h2>", r"## \1\n"),
            (r"<h3[^>]*>(.*?)</h3>", r"### \1\n"),
            (r"<h4[^>]*>(.*?)</h4>", r"#### \1\n"),
            (r"<h5[^>]*>(.*?)</h5>", r"##### \1\n"),
            (r"<h6[^>]*>(.*?)</h6>", r"###### \1\n"),
            (r"<strong[^>]*>(.*?)</strong>", r"**\1**"),
            (r"<b[^>]*>(.*?)</b>", r"**\1**"),
            (r"<em[^>]*>(.*?)</em>", r"*\1*"),
            (r"<i[^>]*>(.*?)</i>", r"*\1*"),
            (r"<code[^>]*>(.*?)</code>", r"`\1`"),
            (r"<br\s*/?>", "\n"),
            (r"</p>", "\n\n"),
            (r"<p[^>]*>", ""),
            (r"<ul[^>]*>", "\n"),
            (r"</ul>", "\n"),
            (r"<ol[^>]*>", "\n"),
            (r"</ol>", "\n"),
            (r"<li[^>]*>", "- "),
            (r"</li>", "\n"),
            (r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", r"\n```\n\1\n```\n"),
            (r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n"),
        ]

        output = text
        for pattern, replacement in conversions:
            output = re.sub(pattern, replacement, output, flags=re.DOTALL | re.IGNORECASE)

        output = re.sub(r"<ri:user[^>]*ri:display-name=\"([^\"]+)\"[^>]*/>", r"\1", output)
        output = re.sub(r"<ri:user[^>]*/>", "Benutzer", output)
        output = re.sub(r"<[^>]+>", "", output)
        return html.unescape(output)


    def _extract_task_metadata(self, text: str) -> dict[str, object]:
        """Extract task counters/mentions from rendered Open/Completed task sections."""
        metadata: dict[str, object] = {}
        open_section = self._extract_section(text, "Open Tasks")
        completed_section = self._extract_section(text, "Completed Tasks")

        open_count, open_mentions = self._count_tasks_and_mentions(open_section)
        completed_count, completed_mentions = self._count_tasks_and_mentions(completed_section)

        if open_count:
            metadata["open_task_count"] = open_count
            metadata["open_task_mentions"] = open_mentions
        if completed_count:
            metadata["completed_task_count"] = completed_count
            metadata["completed_task_mentions"] = completed_mentions
        return metadata

    def _extract_section(self, text: str, section_title: str) -> str:
        pattern = re.compile(rf"^## {re.escape(section_title)}\n(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
        match = pattern.search(text)
        return match.group("body") if match else ""

    def _count_tasks_and_mentions(self, section_text: str) -> tuple[int, list[str]]:
        task_count = len(re.findall(r"^- ", section_text, flags=re.MULTILINE))
        mentions: list[str] = []
        for mention_line in re.findall(r"^\s*Mentions:\s*(.+?)\.\s*$", section_text, flags=re.MULTILINE):
            for raw_name in mention_line.split(","):
                name = raw_name.strip()
                if name and name not in mentions:
                    mentions.append(name)
        return task_count, mentions

    def _cleanup_whitespace(self, text: str) -> str:
        cleaned = re.sub(r"\r\n?", "\n", text)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _remove_empty_headings(self, text: str) -> str:
        output = text
        for level in (3, 2, 1):
            output = self._remove_empty_headings_for_level(output, level)
        return output

    def _remove_empty_headings_for_level(self, text: str, level: int) -> str:
        heading_pattern = re.compile(r"^(#{1,6})\s+.*$")
        target_prefix = "#" * level + " "
        lines = text.split("\n")
        keep_line = [True] * len(lines)

        for idx, line in enumerate(lines):
            if not line.startswith(target_prefix):
                continue

            section_end = len(lines)
            for probe in range(idx + 1, len(lines)):
                match = heading_pattern.match(lines[probe])
                if not match:
                    continue
                if len(match.group(1)) <= level:
                    section_end = probe
                    break

            has_content = any(lines[probe].strip() for probe in range(idx + 1, section_end))
            if not has_content:
                keep_line[idx] = False

        return "\n".join(line for line, keep in zip(lines, keep_line) if keep)
