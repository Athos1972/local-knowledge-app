"""Transformer für JIRA-Exportdaten."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from time import perf_counter
import re

from processing.confluence.link_transformer import LinkTransformer
from processing.confluence.models import TransformWarning
from processing.image_analysis.models import DerivedFileArtifact, ParentDocumentContext
from processing.jira.models import JiraRawIssue, JiraTransformedIssue
from sources.document import stable_hash
from processing.terminology import TerminologyService
from transformers.router import TransformRouter

logger = logging.getLogger(__name__)


class JiraTransformer:
    """Transformiert rohe JIRA-Issues in ingestierbares Markdown."""

    def __init__(self) -> None:
        self._link_transformer = LinkTransformer()
        self._transform_router = TransformRouter()
        self._terminology_service = TerminologyService()

    def finalize_terminology_report(self) -> Path | None:
        """Finalize and write the aggregated terminology candidate report."""
        return self._terminology_service.finalize_candidate_report()

    def transform(self, issue: JiraRawIssue) -> JiraTransformedIssue:
        warnings: list[TransformWarning] = []

        text = issue.description or ""
        text = self._link_transformer.transform(text, source_url=issue.source_url)
        text = self._convert_structure(text)
        text = self._cleanup_whitespace(text)

        lines = [f"# {issue.issue_key}: {issue.summary}", ""]
        if issue.status:
            lines.append(f"- Status: {issue.status}")
        if issue.issue_type:
            lines.append(f"- Typ: {issue.issue_type}")
        if issue.priority:
            lines.append(f"- Priorität: {issue.priority}")
        if issue.assignee:
            lines.append(f"- Assignee: {issue.assignee}")
        if issue.reporter:
            lines.append(f"- Reporter: {issue.reporter}")
        if len(lines) > 2:
            lines.extend(["", "## Beschreibung", ""])
        lines.append(text or "_Keine Beschreibung im Export gefunden._")

        attachment_sections, image_analysis_refs, derived_artifacts = self._render_attachment_content(issue, warnings)
        attachment_stats = self._build_attachment_stats(issue, warnings)
        if attachment_sections:
            lines.extend(["", "## Anhang-Inhalte (extrahiert)", "", *attachment_sections])
        if image_analysis_refs:
            lines.extend(["", "## Abgeleitete Bildanalysen", ""])
            lines.extend(
                f"- [{item.get('attachment_name', 'Bildanalyse')}]({item.get('derived_md_file', '')})"
                for item in image_analysis_refs
                if item.get("derived_md_file")
            )

        body = "\n".join(lines).rstrip() + self._link_transformer.render_attachments(issue.attachments)
        terminology_result = self._terminology_service.apply_to_text(
            body,
            source_type="jira",
            source_ref=issue.source_ref,
        )

        attachment_signature = ",".join(sorted(f"{a.get('name','')}|{a.get('local_path','')}" for a in issue.attachments if isinstance(a, dict)))
        content_hash = stable_hash(
            "|".join(
                [
                    issue.issue_key,
                    issue.summary,
                    issue.description,
                    issue.updated_at or "",
                    ",".join(issue.labels),
                    attachment_signature,
                ]
            )
        )

        return JiraTransformedIssue(
            issue_id=issue.issue_id,
            issue_key=issue.issue_key,
            project_key=issue.project_key,
            summary=issue.summary,
            body_markdown=terminology_result.text,
            source_ref=issue.source_ref,
            source_url=issue.source_url,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            issue_type=issue.issue_type,
            status=issue.status,
            priority=issue.priority,
            assignee=issue.assignee,
            reporter=issue.reporter,
            labels=issue.labels,
            components=issue.components,
            fix_versions=issue.fix_versions,
            attachments=issue.attachments,
            transform_warnings=warnings,
            attachment_stats=attachment_stats,
            image_analysis_refs=image_analysis_refs,
            derived_artifacts=derived_artifacts,
            content_hash=content_hash,
        )

    def _render_attachment_content(
        self,
        issue: JiraRawIssue,
        warnings: list[TransformWarning],
    ) -> tuple[list[str], list[dict[str, object]], list[DerivedFileArtifact]]:
        sections: list[str] = []
        image_analysis_refs: list[dict[str, object]] = []
        derived_artifacts: list[DerivedFileArtifact] = []
        indexed = {Path(path).name: path for path in issue.attachment_paths}
        attachment_timings: dict[str, float] = {}

        for attachment in issue.attachments:
            if not isinstance(attachment, dict):
                continue

            name = str(attachment.get("name") or attachment.get("filename") or attachment.get("title") or "Anhang")
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

            transformer = self._transform_router.resolve(path)
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
                source_system="jira",
                parent_id=issue.issue_key,
                parent_title=issue.summary,
                parent_source_ref=issue.source_ref,
                parent_source_url=issue.source_url,
                parent_output_name=f"{issue.issue_key}__{self._slugify(issue.summary)}.md",
                section_hint="attachments",
                surrounding_text=issue.description,
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
                    "JIRA attachment transformed. issue=%s attachment=%s suffix=%s duration_ms=%.2f",
                    issue.issue_key,
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
            issue.raw_metadata["_attachment_timings_ms"] = attachment_timings
        return sections, image_analysis_refs, derived_artifacts

    def _build_attachment_stats(self, issue: JiraRawIssue, warnings: list[TransformWarning]) -> dict[str, object]:
        suffix_counts: dict[str, int] = {}
        duration_by_suffix_ms: dict[str, float] = {}
        extracted = 0
        raw_timings = issue.raw_metadata.get("_attachment_timings_ms", {})
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

        failed = sum(warning_counts.values())
        return {
            "total": len(issue.attachments),
            "extracted": extracted,
            "failed": failed,
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

    def _convert_structure(self, text: str) -> str:
        conversions = [
            (r"<h1[^>]*>(.*?)</h1>", r"# \1\n"),
            (r"<h2[^>]*>(.*?)</h2>", r"## \1\n"),
            (r"<h3[^>]*>(.*?)</h3>", r"### \1\n"),
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
            (r"<li[^>]*>", "- "),
            (r"</li>", "\n"),
        ]

        output = text
        for pattern, replacement in conversions:
            output = re.sub(pattern, replacement, output, flags=re.DOTALL | re.IGNORECASE)

        output = re.sub(r"<[^>]+>", "", output)
        return html.unescape(output)

    def _cleanup_whitespace(self, text: str) -> str:
        cleaned = re.sub(r"\r\n?", "\n", text)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _slugify(value: str) -> str:
        lower = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9äöüß\-\s]", "", lower)
        compact = re.sub(r"\s+", "-", normalized)
        return compact.strip("-") or "untitled"
