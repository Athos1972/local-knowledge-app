"""Tabellenkonvertierung für Confluence-Storage-HTML."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
import re

from processing.confluence.models import TransformWarning


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
        if tag == "tr":
            self._current_row = []
        if tag in {"td", "th"}:
            self._in_cell = True
            self._cell_buffer = []
            self._current_cell_is_header = tag == "th"
            attr_map = {key: value for key, value in attrs}
            self._current_colspan = self._parse_span(attr_map.get("colspan"))
            self._current_rowspan = self._parse_span(attr_map.get("rowspan"))
            if self._current_colspan > 1 or self._current_rowspan > 1:
                self.has_span_complexity = True
            self._current_cell_complex = False
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

    def transform(self, text: str) -> tuple[str, list[TransformWarning], dict[str, str], int]:
        warnings: list[TransformWarning] = []
        key_value_properties: dict[str, str] = {}
        key_value_count = 0

        def replace_table(match: re.Match[str]) -> str:
            table_html = match.group(0)
            parser = _TableParser()
            parser.feed(table_html)
            parsed_table = ParsedTable(
                rows=parser.rows,
                has_nested_table=parser.has_nested_table,
                has_span_complexity=parser.has_span_complexity,
            )
            result = self._render_table(parsed_table)
            if result.warning:
                warnings.append(result.warning)
            if result.key_value_properties:
                nonlocal key_value_count
                key_value_count += 1
                key_value_properties.update(result.key_value_properties)
            return result.markdown

        transformed = re.sub(r"<table\b[^>]*>.*?</table>", replace_table, text, flags=re.DOTALL | re.IGNORECASE)
        logger.debug("Tabellenanalyse abgeschlossen: key_value_tables=%s", key_value_count)
        return transformed, warnings, key_value_properties, key_value_count

    def _render_table(self, table: ParsedTable) -> TableTransformResult:
        if not table.rows:
            return TableTransformResult(markdown="")

        row_count = len(table.rows)
        col_count = max(len(row) for row in table.rows)

        if self._is_key_value_table(table):
            markdown, properties = self._as_key_value(table.rows)
            return TableTransformResult(markdown=markdown, key_value_properties=properties)
        if row_count <= 15 and col_count <= 6:
            return TableTransformResult(markdown=self._as_markdown_table(table.rows))

        return TableTransformResult(
            markdown="\n[COMPLEX_TABLE: Konvertierung nicht sicher möglich]\n",
            warning=TransformWarning(
                code="complex_table",
                message="Komplexe Tabelle konnte nicht sicher als Markdown gerendert werden.",
            ),
        )

    def _is_key_value_table(self, table: ParsedTable) -> bool:
        """Erkennt konservativ Key-Value-/Page-Properties-Tabellen."""
        rows = table.rows
        if len(rows) < 2:
            return False
        if any(len(row) != 2 for row in rows):
            return False
        if table.has_nested_table or table.has_span_complexity:
            return False
        if any(cell.has_complex_structure for row in rows for cell in row):
            return False

        if self._looks_like_explicit_header_row(rows[0]):
            return False

        label_like_count = 0
        non_empty_value_count = 0
        for row in rows:
            label = row[0].text.strip()
            value = row[1].text.strip()
            if self._is_label_like(label):
                label_like_count += 1
            if value:
                non_empty_value_count += 1

        ratio_labels = label_like_count / len(rows)
        ratio_values = non_empty_value_count / len(rows)
        return ratio_labels >= 0.8 and ratio_values >= 0.6

    def _looks_like_explicit_header_row(self, row: list[TableCell]) -> bool:
        """Erkennt tabellarische Kopfzeilen wie `Key | Value` konservativ."""
        if len(row) != 2:
            return False
        left = self._normalize_frontmatter_key(row[0].text)
        right = self._normalize_frontmatter_key(row[1].text)
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
        lines = [""]
        properties: dict[str, str] = {}
        for row in rows:
            key_raw = row[0].text.strip()
            value_raw = row[1].text.strip()
            lines.append(f"- **{key_raw}:** {value_raw}")
            normalized_key = self._normalize_frontmatter_key(key_raw)
            if normalized_key and normalized_key not in properties and value_raw:
                properties[normalized_key] = value_raw
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
    def _normalize_frontmatter_key(value: str) -> str:
        """Normalisiert einen Label-Text zu einem snake_case-Key."""
        lowered = value.strip().lower()
        lowered = (
            lowered.replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
        )
        normalized = re.sub(r"[^a-z0-9\s-]", "", lowered)
        collapsed = re.sub(r"[-\s]+", "_", normalized).strip("_")
        return collapsed

    @staticmethod
    def _escape_cell(cell: str) -> str:
        return cell.strip().replace("|", "\\|")
