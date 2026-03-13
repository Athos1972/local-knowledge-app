"""Transformation von Confluence-Makros in Markdown-freundliche Darstellungen."""

from __future__ import annotations

import re

from processing.confluence.models import TransformWarning

SUPPORTED_CALLOUTS = {"info", "note", "warning", "tip", "panel"}
SUPPORTED_SIMPLE = {
    "expand",
    "details",
    "status",
    "task-list",
    "toc",
    "plantuml",
    "plantumlrender",
    "table-filter",
    "jira",
    "view-file",
}
VALID_MACRO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


class MacroTransformer:
    """Konvertiert ausgewählte Confluence-Makros in MVP-Markdown."""

    def transform(self, text: str) -> tuple[str, list[TransformWarning], list[str]]:
        """Transformiert bekannte Makros und meldet unbekannte Makros als Warnung."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        transformed = text
        max_iterations = 15
        for _ in range(max_iterations):
            previous = transformed
            transformed = self._transform_known_macros(transformed, warnings)
            transformed = self._unwrap_unsupported_macros(transformed, warnings, unsupported)
            if transformed == previous:
                break

        return transformed, warnings, unsupported

    def _transform_known_macros(self, text: str, warnings: list[TransformWarning]) -> str:
        transformed = text
        for macro in SUPPORTED_CALLOUTS:
            transformed = self._replace_callout_macro(transformed, macro)

        transformed = self._replace_expand_details_macro(transformed)
        transformed = self._replace_status_macro(transformed)
        transformed = self._replace_task_items(transformed)
        transformed = self._remove_toc_macro(transformed)
        transformed = self._replace_plantuml_macro(transformed, warnings)
        transformed = self._unwrap_table_filter_macro(transformed, warnings)
        transformed = self._replace_jira_macro(transformed, warnings)
        transformed = self._replace_view_file_macro(transformed, warnings)
        return transformed

    def _unwrap_unsupported_macros(
        self,
        text: str,
        warnings: list[TransformWarning],
        unsupported: list[str],
    ) -> str:
        macro_pattern = re.compile(
            r"<ac:structured-macro\b(?P<attrs>[^>]*)>(?P<body>.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def replace_unsupported(match: re.Match[str]) -> str:
            macro_name = self._extract_macro_name(match.group("attrs"), warnings)
            if macro_name in SUPPORTED_CALLOUTS | SUPPORTED_SIMPLE:
                return match.group(0)

            unsupported.append(macro_name)
            warnings.append(
                TransformWarning(
                    code="unsupported_macro",
                    message=f"Nicht unterstütztes Makro erkannt: {macro_name}",
                    context=macro_name,
                )
            )
            inner = self._extract_macro_inner_content(match.group("body"))
            return f"\n{inner}\n" if inner.strip() else ""

        return macro_pattern.sub(replace_unsupported, text)

    def _extract_macro_inner_content(self, body: str) -> str:
        rich_text_match = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", body, re.DOTALL)
        if rich_text_match:
            return rich_text_match.group(1)

        plain_text_match = re.search(r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>", body, re.DOTALL)
        if plain_text_match:
            return plain_text_match.group(1)

        parameter_content = re.sub(r"<ac:parameter[^>]*>.*?</ac:parameter>", "", body, flags=re.DOTALL)
        return parameter_content

    def _replace_callout_macro(self, text: str, macro_name: str) -> str:
        pattern = re.compile(
            rf"<ac:structured-macro[^>]*ac:name=\"{re.escape(macro_name)}\"[^>]*>.*?<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            body = self._strip_tags(match.group(1)).strip()
            label = macro_name.upper()
            lines = [f"> **{label}:** {line}" if idx == 0 else f"> {line}" for idx, line in enumerate(body.splitlines() or [""])]
            return "\n" + "\n".join(lines).strip() + "\n"

        return pattern.sub(repl, text)

    def _replace_expand_details_macro(self, text: str) -> str:
        """Rendert expand/details-Makros als Abschnitt mit Überschrift."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"(?:expand|details)\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            title = self._extract_parameter(block, "title") or "Details"
            body_match = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", block, re.DOTALL)
            body = body_match.group(1).strip() if body_match else ""
            return f"\n## {title}\n\n{body}\n"

        return pattern.sub(repl, text)

    def _remove_toc_macro(self, text: str) -> str:
        """Entfernt TOC-Makros bewusst, da sie für den Inhalt nicht relevant sind."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"toc\"[^>]*>.*?</ac:structured-macro>",
            re.DOTALL,
        )
        return pattern.sub("", text)

    def _replace_plantuml_macro(self, text: str, warnings: list[TransformWarning]) -> str:
        """Erhält PlantUML-Inhalt als fenced Codeblock."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"(?:plantuml|plantumlrender)\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            plain_text_match = re.search(r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>", block, re.DOTALL)
            if plain_text_match:
                source = plain_text_match.group(1).strip()
                if source:
                    return f"\n```plantuml\n{source}\n```\n"

            warnings.append(
                TransformWarning(
                    code="degraded_macro_rendering",
                    message="PlantUML-Inhalt konnte nicht vollständig extrahiert werden.",
                    context="plantuml",
                )
            )
            return "\n[PLANTUML_BLOCK]\nPlantUML-Inhalt konnte nicht vollständig extrahiert werden.\n"

        return pattern.sub(repl, text)

    def _unwrap_table_filter_macro(self, text: str, warnings: list[TransformWarning]) -> str:
        """Behandelt table-filter als Hülle und reicht den Inhalt weiter."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"table-filter\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            body_match = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", block, re.DOTALL)
            if body_match:
                return body_match.group(1)
            warnings.append(
                TransformWarning(
                    code="degraded_macro_rendering",
                    message="table-filter konnte keinen verwertbaren Inhalt liefern.",
                    context="table-filter",
                )
            )
            return ""

        return pattern.sub(repl, text)

    def _replace_jira_macro(self, text: str, warnings: list[TransformWarning]) -> str:
        """Rendert Jira-Makros als lesbaren Hinweis."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"jira\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            key = self._extract_parameter(block, "key") or self._extract_parameter(block, "jqlQuery")
            url = self._extract_parameter(block, "server") or self._extract_url(block)
            if key and url:
                return f"\n**Jira-Vorgang:** [{key}]({url})\n"
            if key:
                return f"\n**Jira-Vorgang:** {key}\n"
            if url:
                return f"\n**Jira-Vorgang:** {url}\n"

            warnings.append(
                TransformWarning(
                    code="degraded_macro_rendering",
                    message="Jira-Makro ohne verwertbare Details erkannt.",
                    context="jira",
                )
            )
            return "\n[JIRA_BLOCK]\nJira-Inhalt konnte nicht eindeutig extrahiert werden.\n"

        return pattern.sub(repl, text)

    def _replace_view_file_macro(self, text: str, warnings: list[TransformWarning]) -> str:
        """Rendert view-file-Makros als Datei-Hinweis."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"view-file\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            file_name = self._extract_parameter(block, "name") or self._extract_attachment_filename(block)
            url = self._extract_url(block)
            if file_name and url:
                return f"\n**Datei:** [{file_name}]({url})\n"
            if file_name:
                return f"\n**Datei:** {file_name}\n"
            if url:
                return f"\n**Datei:** {url}\n"

            warnings.append(
                TransformWarning(
                    code="degraded_macro_rendering",
                    message="view-file-Makro ohne Dateidetails erkannt.",
                    context="view-file",
                )
            )
            return "\n[FILE_BLOCK]\nDatei-Referenz konnte nicht eindeutig extrahiert werden.\n"

        return pattern.sub(repl, text)

    def _replace_status_macro(self, text: str) -> str:
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"status\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            title_match = re.search(r"<ac:parameter[^>]*ac:name=\"title\"[^>]*>(.*?)</ac:parameter>", block, re.DOTALL)
            value = self._strip_tags(title_match.group(1)).strip() if title_match else "Unbekannt"
            return f"**Status:** {value}"

        return pattern.sub(repl, text)

    def _replace_task_items(self, text: str) -> str:
        text = re.sub(r"<ac:task-list>", "\n", text)
        text = re.sub(r"</ac:task-list>", "\n", text)
        text = re.sub(r"<ac:task>\s*", "", text)
        text = re.sub(r"\s*</ac:task>", "\n", text)
        text = re.sub(r"<ac:task-status>complete</ac:task-status>", "- [x] ", text)
        text = re.sub(r"<ac:task-status>incomplete</ac:task-status>", "- [ ] ", text)
        text = re.sub(r"<ac:task-body>", "", text)
        text = re.sub(r"</ac:task-body>", "", text)
        return text

    @staticmethod
    def _strip_tags(value: str) -> str:
        stripped = re.sub(r"<[^>]+>", "", value)
        return re.sub(r"\s+", " ", stripped).strip()

    def _extract_parameter(self, block: str, name: str) -> str | None:
        """Extrahiert einen Parameterwert aus einem Makro-Block."""
        match = re.search(
            rf"<ac:parameter[^>]*ac:name=\"{re.escape(name)}\"[^>]*>(.*?)</ac:parameter>",
            block,
            re.DOTALL,
        )
        if not match:
            return None
        value = self._strip_tags(match.group(1)).strip()
        return value or None

    def _extract_url(self, block: str) -> str | None:
        """Extrahiert eine URL aus typischen Link-Elementen innerhalb eines Makros."""
        for pattern in [r'<ri:url[^>]*ri:value="([^"]+)"', r'<a[^>]*href="([^"]+)"']:
            match = re.search(pattern, block, re.DOTALL)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return None

    def _extract_attachment_filename(self, block: str) -> str | None:
        """Extrahiert Dateinamen aus Anhangsreferenzen."""
        match = re.search(r'<ri:attachment[^>]*ri:filename="([^"]+)"', block)
        if not match:
            return None
        filename = match.group(1).strip()
        return filename or None

    def _extract_macro_name(self, attrs: str, warnings: list[TransformWarning]) -> str:
        """Liest den Makronamen robust aus Attributen und validiert ihn."""
        name_match = re.search(r'ac:name="([^"]+)"', attrs)
        if not name_match:
            warnings.append(
                TransformWarning(
                    code="macro_name_parse_error",
                    message="Makro ohne auslesbaren Namen erkannt.",
                    context="unknown_macro",
                )
            )
            return "unknown_macro"

        macro_name = name_match.group(1).strip()
        if VALID_MACRO_NAME_PATTERN.match(macro_name):
            return macro_name

        warnings.append(
            TransformWarning(
                code="macro_name_parse_error",
                message=f"Ungültiger Makroname erkannt und auf unknown_macro gesetzt: {macro_name[:80]}",
                context="unknown_macro",
            )
        )
        return "unknown_macro"
