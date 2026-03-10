"""Tabellenkonvertierung für Confluence-Storage-HTML."""

from __future__ import annotations

from html.parser import HTMLParser
import re

from processing.confluence.models import TransformWarning


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_buffer: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        if tag in {"td", "th"}:
            self._in_cell = True
            self._cell_buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            cell = re.sub(r"\s+", " ", "".join(self._cell_buffer).strip())
            self._current_row.append(cell)
            self._cell_buffer = []
            self._in_cell = False
        elif tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = []


class TableTransformer:
    """Klassifiziert Tabellen und rendert konservativ in Markdown."""

    def transform(self, text: str) -> tuple[str, list[TransformWarning]]:
        warnings: list[TransformWarning] = []

        def replace_table(match: re.Match[str]) -> str:
            table_html = match.group(0)
            parser = _TableParser()
            parser.feed(table_html)
            replacement, warning = self._render_table(parser.rows)
            if warning:
                warnings.append(warning)
            return replacement

        transformed = re.sub(r"<table\b[^>]*>.*?</table>", replace_table, text, flags=re.DOTALL | re.IGNORECASE)
        return transformed, warnings

    def _render_table(self, rows: list[list[str]]) -> tuple[str, TransformWarning | None]:
        if not rows:
            return "", None

        row_count = len(rows)
        col_count = max(len(row) for row in rows)
        if col_count <= 2 and row_count <= 20:
            return self._as_key_value(rows), None
        if row_count <= 15 and col_count <= 6:
            return self._as_markdown_table(rows), None

        return (
            "\n[COMPLEX_TABLE: Konvertierung nicht sicher möglich]\n",
            TransformWarning(
                code="complex_table",
                message="Komplexe Tabelle konnte nicht sicher als Markdown gerendert werden.",
            ),
        )

    def _as_key_value(self, rows: list[list[str]]) -> str:
        lines = [""]
        for row in rows:
            if len(row) >= 2:
                lines.append(f"- **{row[0]}:** {row[1]}")
            elif row:
                lines.append(f"- {row[0]}")
        lines.append("")
        return "\n".join(lines)

    def _as_markdown_table(self, rows: list[list[str]]) -> str:
        width = max(len(row) for row in rows)
        normalized = [row + [""] * (width - len(row)) for row in rows]

        header = normalized[0]
        body = normalized[1:] if len(normalized) > 1 else []

        lines = [""]
        lines.append("| " + " | ".join(self._escape_cell(cell) for cell in header) + " |")
        lines.append("| " + " | ".join(["---"] * width) + " |")
        for row in body:
            lines.append("| " + " | ".join(self._escape_cell(cell) for cell in row) + " |")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _escape_cell(cell: str) -> str:
        return cell.strip().replace("|", "\\|")
