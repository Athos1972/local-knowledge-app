"""Tabellenkonvertierung für Confluence-Storage-HTML."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
import re

from processing.confluence.models import ConfluenceExtraDocument, TransformWarning
from processing.confluence.page_properties import (
    PropertyPromotionRule,
    filtered_renderable_property_keys,
    match_promoted_key,
    normalize_property_key,
    normalize_property_value,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TableCell:
    """Repräsentiert eine einzelne Tabellenzelle inklusive Strukturmerkmalen."""

    text: str
    is_header: bool = False
    colspan: int = 1
    rowspan: int = 1
    has_complex_structure: bool = False


@dataclass(slots=True)
class ParsedTable:
    """Interne, strukturierte Darstellung einer geparsten Tabelle."""

    rows: list[list[TableCell]] = field(default_factory=list)
    has_nested_table: bool = False
    has_span_complexity: bool = False


@dataclass(slots=True)
class TableTransformResult:
    """Ergebnis eines Tabellen-Transforms."""

    markdown: str
    warning: TransformWarning | None = None
    key_value_properties: dict[str, str] = field(default_factory=dict)
    extra_document: ConfluenceExtraDocument | None = None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[TableCell]] = []
        self._current_row: list[TableCell] = []
        self._cell_buffer: list[str] = []
        self._in_cell = False
        self._current_cell_is_header = False
        self._current_colspan = 1
        self._current_rowspan = 1
        self._current_cell_complex = False
        self.has_nested_table = False
        self.has_span_complexity = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs}
        if tag == "tr":
            self._current_row = []
        if tag in {"td", "th"}:
            self._in_cell = True
            self._cell_buffer = []
            self._current_cell_is_header = tag == "th"
            self._current_colspan = self._parse_span(attr_map.get("colspan"))
            self._current_rowspan = self._parse_span(attr_map.get("rowspan"))
            if self._current_colspan > 1 or self._current_rowspan > 1:
                self.has_span_complexity = True
            self._current_cell_complex = False
            return

        if self._in_cell and tag == "ri:user":
            display_name = (attr_map.get("ri:display-name") or "").strip()
            if display_name:
                self._cell_buffer.append(display_name)
            else:
                self._cell_buffer.append("Benutzer")
            return

        if self._in_cell and tag == "table":
            self.has_nested_table = True
            self._current_cell_complex = True
            return

        if self._in_cell and tag in {"ul", "ol", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._current_cell_complex = True

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            cell = re.sub(r"\s+", " ", "".join(self._cell_buffer).strip())
            self._current_row.append(
                TableCell(
                    text=cell,
                    is_header=self._current_cell_is_header,
                    colspan=self._current_colspan,
                    rowspan=self._current_rowspan,
                    has_complex_structure=self._current_cell_complex,
                )
            )
            self._cell_buffer = []
            self._in_cell = False
        elif tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = []

    @staticmethod
    def _parse_span(value: str | None) -> int:
        """Parst colspan/rowspan robust als positive Ganzzahl."""
        if value is None:
            return 1
        try:
            parsed = int(value)
        except ValueError:
            return 1
        return parsed if parsed > 0 else 1


class TableTransformer:
    """Klassifiziert Tabellen und rendert konservativ in Markdown."""

    def __init__(self, promotion_rules: dict[str, PropertyPromotionRule] | None = None) -> None:
        self._promotion_rules = promotion_rules or {}

    def transform(
        self,
        text: str,
        *,
        page_id: str,
        page_title: str,
        page_slug: str,
        source_url: str | None,
        labels: list[str],
        parent_title: str | None,
        content_hash: str,
        warnings: list[TransformWarning],
    ) -> tuple[str, dict[str, str], int, list[ConfluenceExtraDocument]]:
        key_value_properties: dict[str, str] = {}
        key_value_count = 0
        complex_table_index = 0
        extra_documents: list[ConfluenceExtraDocument] = []

        def replace_table(match: re.Match[str]) -> str:
            nonlocal key_value_count, complex_table_index
            table_html = match.group(0)
            parser = _TableParser()
            parser.feed(table_html)
            parsed_table = ParsedTable(
                rows=parser.rows,
                has_nested_table=parser.has_nested_table,
                has_span_complexity=parser.has_span_complexity,
            )
            result = self._render_table(
                parsed_table,
                page_id=page_id,
                page_title=page_title,
                page_slug=page_slug,
                source_url=source_url,
                labels=labels,
                parent_title=parent_title,
                content_hash=content_hash,
                complex_table_index=complex_table_index + 1,
            )
            if result.warning:
                warnings.append(result.warning)
            if result.key_value_properties:
                key_value_count += 1
                key_value_properties.update(result.key_value_properties)
            if result.extra_document:
                complex_table_index += 1
                extra_documents.append(result.extra_document)
            return result.markdown

        transformed = re.sub(r"<table\b[^>]*>.*?</table>", replace_table, text, flags=re.DOTALL | re.IGNORECASE)
        logger.debug(
            "Tabellenanalyse abgeschlossen: key_value_tables=%s, complex_tables=%s",
            key_value_count,
            len(extra_documents),
        )
        return transformed, key_value_properties, key_value_count, extra_documents

    def _render_table(
        self,
        table: ParsedTable,
        *,
        page_id: str,
        page_title: str,
        page_slug: str,
        source_url: str | None,
        labels: list[str],
        parent_title: str | None,
        content_hash: str,
        complex_table_index: int,
    ) -> TableTransformResult:
        if not table.rows:
            return TableTransformResult(markdown="")

        row_count = len(table.rows)
        col_count = max(len(row) for row in table.rows)

        if self._is_key_value_table(table):
            markdown, properties = self._as_key_value(table.rows)
            return TableTransformResult(markdown=markdown, key_value_properties=properties)
        if row_count <= 15 and col_count <= 6 and not table.has_nested_table and not table.has_span_complexity:
            return TableTransformResult(markdown=self._as_markdown_table(table.rows))

        file_name = f"{page_id}__{page_slug}__table_{complex_table_index:02d}.md"
        context = f"rows={row_count}, cols={col_count}, nested={table.has_nested_table}, spans={table.has_span_complexity}"
        markdown = (
            f"\n[Komplexe Tabelle ausgelagert: {file_name}]\n"
            f"Hinweis: {context}.\n"
        )
        artifact = self._build_complex_table_document(
            file_name=file_name,
            table=table,
            page_id=page_id,
            page_title=page_title,
            source_url=source_url,
            labels=labels,
            parent_title=parent_title,
            content_hash=content_hash,
            table_index=complex_table_index,
        )
        return TableTransformResult(
            markdown=markdown,
            extra_document=artifact,
        )

    def _build_complex_table_document(
        self,
        *,
        file_name: str,
        table: ParsedTable,
        page_id: str,
        page_title: str,
        source_url: str | None,
        labels: list[str],
        parent_title: str | None,
        content_hash: str,
        table_index: int,
    ) -> ConfluenceExtraDocument:
        row_count = len(table.rows)
        col_count = max(len(row) for row in table.rows)
        lines = [
            f"# Tabelle aus: {page_title}",
            "",
            "Diese Tabelle wurde wegen komplexer Struktur aus der Hauptseite ausgelagert.",
            f"Erkannte Struktur: Zeilen={row_count}, Spalten={col_count}, nested_table={table.has_nested_table}, spans={table.has_span_complexity}.",
            "",
            "## Inhalt (konservativ abgeflacht)",
            "",
        ]
        lines.extend(
            self._flatten_rows(
                table.rows,
                restrict_to_key_value_columns=self._is_page_properties_title(page_title),
            )
        )
        if not lines[-1]:
            body = "\n".join(lines)
        else:
            body = "\n".join(lines) + "\n"

        metadata = {
            "title": f"Tabelle {table_index:02d} aus {page_title}",
            "source_type": "confluence",
            "doc_type": "confluence_table",
            "page_id": page_id,
            "parent_title": parent_title or "",
            "table_index": table_index,
            "table_complexity": True,
            "source_url": source_url or "",
            "labels": labels,
            "content_hash": content_hash,
            "transform_warnings": ["complex_table"],
        }
        return ConfluenceExtraDocument(
            file_name=file_name,
            title=metadata["title"],
            doc_type="confluence_table",
            body_markdown=body,
            metadata=metadata,
        )

    def _flatten_rows(self, rows: list[list[TableCell]], *, restrict_to_key_value_columns: bool = False) -> list[str]:
        if not rows:
            return ["- Keine auslesbaren Zeilen gefunden.", ""]

        rows_to_render = rows
        if restrict_to_key_value_columns:
            projected_rows = self._project_key_value_rows(rows)
            if projected_rows:
                rows_to_render = projected_rows

        has_header = all(cell.is_header for cell in rows_to_render[0]) and len(rows_to_render) > 1
        if has_header:
            headers = [cell.text.strip() or f"Spalte {idx + 1}" for idx, cell in enumerate(rows_to_render[0])]
            lines = []
            for row_idx, row in enumerate(rows_to_render[1:], start=1):
                pairs = []
                for col_idx, cell in enumerate(row):
                    key = headers[col_idx] if col_idx < len(headers) else f"Spalte {col_idx + 1}"
                    value = cell.text.strip() or "(leer)"
                    if cell.colspan > 1 or cell.rowspan > 1:
                        value = f"{value} [span c{cell.colspan}/r{cell.rowspan}]"
                    pairs.append(f"{key}={value}")
                lines.append(f"- Zeile {row_idx}: " + " | ".join(pairs))
            return lines + [""]

        fallback_lines = []
        for row_idx, row in enumerate(rows_to_render, start=1):
            values = []
            for col_idx, cell in enumerate(row, start=1):
                value = cell.text.strip() or "(leer)"
                if cell.colspan > 1 or cell.rowspan > 1:
                    value = f"{value} [span c{cell.colspan}/r{cell.rowspan}]"
                values.append(f"Zelle {col_idx}={value}")
            fallback_lines.append(f"- Originalzeile {row_idx}: " + " | ".join(values))
        return fallback_lines + [""]

    def _is_page_properties_title(self, title: str) -> bool:
        normalized = normalize_property_key(title)
        return "seiteneigenschaft" in normalized

    def _is_key_value_table(self, table: ParsedTable) -> bool:
        """Erkennt konservativ Key-Value-/Page-Properties-Tabellen."""
        projected_rows = self._project_key_value_rows(table.rows)
        if projected_rows is None or not projected_rows:
            return False
        if table.has_nested_table or table.has_span_complexity:
            return False
        if any(cell.has_complex_structure for row in projected_rows for cell in row):
            return False

        if self._looks_like_explicit_header_row(projected_rows[0]):
            return False

        label_like_count = 0
        non_empty_value_count = 0
        for row in projected_rows:
            label = row[0].text.strip()
            value = row[1].text.strip()
            if self._is_label_like(label):
                label_like_count += 1
            if value:
                non_empty_value_count += 1

        ratio_labels = label_like_count / len(projected_rows)
        ratio_values = non_empty_value_count / len(projected_rows)
        return ratio_labels >= 0.8 and ratio_values >= 0.6

    def _project_key_value_rows(self, rows: list[list[TableCell]]) -> list[list[TableCell]] | None:
        """Projiziert Tabellenzeilen auf Key-Value-Paare.

        Unterstützt neben klassischen 2-Spalten-Tabellen auch Header-Spalten-Tabellen,
        bei denen nach der ersten Datenspalte weitere Spalten folgen können.
        """
        if not rows:
            return None

        if all(len(row) == 2 for row in rows):
            return rows

        has_additional_columns = any(len(row) > 2 for row in rows)
        if not has_additional_columns:
            return None
        if not all(len(row) >= 2 and row[0].is_header for row in rows):
            return None

        return [[row[0], row[1]] for row in rows]

    def _looks_like_explicit_header_row(self, row: list[TableCell]) -> bool:
        """Erkennt tabellarische Kopfzeilen wie `Key | Value` konservativ."""
        if len(row) != 2:
            return False
        left = normalize_property_key(row[0].text)
        right = normalize_property_key(row[1].text)
        return left in {"key", "field", "name", "property"} and right in {"value", "wert"}

    def _is_label_like(self, value: str) -> bool:
        """Prüft, ob eine Zelle wie ein kurzes Label aussieht."""
        compact = re.sub(r"\s+", " ", value.strip())
        if not compact:
            return False
        if len(compact) > 40:
            return False
        if len(compact.split(" ")) > 6:
            return False
        return bool(re.search(r"[A-Za-zÄÖÜäöüß0-9]", compact))

    def _as_key_value(self, rows: list[list[TableCell]]) -> tuple[str, dict[str, str]]:
        projected_rows = self._project_key_value_rows(rows) or rows
        lines = [""]
        properties: dict[str, str] = {}
        key_value_pairs: list[tuple[str, str]] = []
        for row in projected_rows:
            key_raw = row[0].text.strip()
            value_raw = row[1].text.strip()
            key_value_pairs.append((key_raw, value_raw))

            promoted_match = match_promoted_key(key_raw, self._promotion_rules)
            if promoted_match:
                canonical_key, rule = promoted_match
                normalized_value = normalize_property_value(value_raw, list_value=rule.list_value)
                if normalized_value is not None and canonical_key not in properties:
                    if isinstance(normalized_value, list):
                        properties[canonical_key] = ", ".join(normalized_value)
                    else:
                        properties[canonical_key] = normalized_value
                continue

            normalized_key = normalize_property_key(key_raw)
            if normalized_key and normalized_key not in properties and value_raw:
                properties[normalized_key] = value_raw

        hidden_keys = filtered_renderable_property_keys(key_value_pairs, self._promotion_rules)
        for key_raw, value_raw in key_value_pairs:
            if key_raw in hidden_keys:
                continue
            lines.append(f"- **{key_raw}:** {value_raw}")

        lines.append("")
        return "\n".join(lines), properties

    def _as_markdown_table(self, rows: list[list[TableCell]]) -> str:
        width = max(len(row) for row in rows)
        normalized = [row + [TableCell(text="")] * (width - len(row)) for row in rows]

        header = normalized[0]
        body = normalized[1:] if len(normalized) > 1 else []

        lines = [""]
        lines.append("| " + " | ".join(self._escape_cell(cell.text) for cell in header) + " |")
        lines.append("| " + " | ".join(["---"] * width) + " |")
        for row in body:
            lines.append("| " + " | ".join(self._escape_cell(cell.text) for cell in row) + " |")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _escape_cell(cell: str) -> str:
        return cell.strip().replace("|", "\\|")
