"""Transformation von Confluence-Makros in Markdown-freundliche Darstellungen."""

from __future__ import annotations

import html
import logging
import re
from collections import Counter
from dataclasses import dataclass

from processing.confluence.models import TransformWarning

SUPPORTED_CALLOUTS = {"info", "note", "warning", "tip", "panel"}
IGNORED_MACROS = {
    "contentbylabel",
    "classifications-hierarchy",
    "classifications-category",
    "anchor",
    "create-from-template",
    "livesearch",
    "profile",
    "tasks-report-macro",
    "children",
    "classifications-status",
    "detailssummary",
    "content-report-table",
    "table-excerpt",
    "table-excerpt-include",
    "attachments",
    "table-joiner",
    "excerpt",
    "gadget",
    "multiexcerpt-include",
    "change-history",
    "include",
    "pagetree",
    "recently-updated",
    "c4c-property-report",
    "lastpageupdate",
    "glossary-navigation-bar",
    "macrosuite-button",
    "excerpt-include",
    "drawio",
    "draw.io",
    "diagrams.net",
    "inc-drawio",
}
SUPPORTED_SIMPLE = {
    "expand",
    "details",
    "status",
    "task-list",
    "toc",
    "plantuml",
    "plantumlrender",
    "table-filter",
    "u7",
    "tablefilter",
    "table-chart",
    "tablechart",
    "table-transformer",
    "jira",
    "view-file",
    "details-summary",
    "page-properties-report",
    "column",
    "multiexcerpt",
    "macrosuite-cards",
    "classifications-combined-taxonomy",
    "macrosuite-panel",
    "section",
    "pivot-table",
    "code",
    "flowchart",
}
VALID_MACRO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
TASK_LIST_PATTERN = re.compile(r"<ac:task-list>(.*?)</ac:task-list>", re.DOTALL | re.IGNORECASE)
TASK_ITEM_PATTERN = re.compile(r"<ac:task>(.*?)</ac:task>", re.DOTALL | re.IGNORECASE)
MENTION_PATTERN = re.compile(r'<ri:user[^>]*ri:display-name="([^"]+)"[^>]*/?>', re.IGNORECASE)
URL_PATTERNS = [r'<ri:url[^>]*ri:value="([^"]+)"', r'<a[^>]*href="([^"]+)"']
DUE_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
TRIVIAL_TASK_TERMS = {
    "fyi",
    "ok",
    "okay",
    "done",
    "?",
    "bitte ansehen",
    "siehe oben",
    "passt",
    "erledigt",
    "anschauen",
    "bitte prüfen",
    "prüfen",
}
DECISION_SIGNALS = {
    "bestätigt",
    "freigegeben",
    "genehmigt",
    "reviewed",
    "approved",
    "abgenommen",
    "entschieden",
    "akzeptiert",
}
DOMAIN_SIGNALS = {
    "architektur",
    "schnittstelle",
    "integration",
    "s/4",
    "utilities",
    "emma",
    "cr",
    "review",
    "abnahme",
    "freigabe",
    "entscheidung",
}

logger = logging.getLogger(__name__)
@dataclass(slots=True)
class ConfluenceTaskItem:
    raw_text: str
    cleaned_text: str
    status: str
    assignees: list[str]
    links: list[str]
    due_date: str | None
    contains_decision_signal: bool
    contains_domain_signal: bool
    keep_reason: str = ""
    drop_reason: str = ""


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

        transformed = self._replace_status_macro(transformed)
        transformed = self._replace_expand_details_macro(transformed)
        transformed = self._replace_task_items(transformed)
        transformed = self._remove_toc_macro(transformed)
        transformed = self._remove_placeholder_macro(transformed)
        transformed = self._remove_ignored_macros(transformed)
        transformed = self._remove_page_properties_report_macro(transformed)
        transformed = self._replace_plantuml_macro(transformed, warnings)
        transformed = self._unwrap_table_like_macro(transformed, "table-filter")
        transformed = self._unwrap_table_like_macro(transformed, "tablefilter")
        transformed = self._unwrap_table_like_macro(transformed, "table-chart")
        transformed = self._unwrap_table_like_macro(transformed, "tablechart")
        transformed = self._unwrap_table_like_macro(transformed, "table-transformer")
        transformed = self._unwrap_table_like_macro(transformed, "column")
        transformed = self._unwrap_table_like_macro(transformed, "multiexcerpt")
        transformed = self._unwrap_table_like_macro(transformed, "macrosuite-cards")
        transformed = self._unwrap_table_like_macro(transformed, "classifications-combined-taxonomy")
        transformed = self._unwrap_table_like_macro(transformed, "macrosuite-panel")
        transformed = self._unwrap_table_like_macro(transformed, "section")
        transformed = self._unwrap_table_like_macro(transformed, "pivot-table")
        transformed = self._unwrap_macro_content(transformed, "code")
        transformed = self._unwrap_macro_content(transformed, "flowchart")
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
            if self._is_supported_macro(macro_name):
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

    def _remove_placeholder_macro(self, text: str) -> str:
        """Entfernt Formularvorlagetexte vollständig (<ac:placeholder>...</ac:placeholder>)."""
        without_block = re.sub(r"<ac:placeholder\b[^>]*>.*?</ac:placeholder>", "", text, flags=re.DOTALL | re.IGNORECASE)
        return re.sub(r"<ac:placeholder\b[^>]*/>", "", without_block, flags=re.IGNORECASE)

    def _remove_ignored_macros(self, text: str) -> str:
        """Entfernt explizit ignorierte Makros ohne Warnung und ohne Ersatzinhalt."""
        output = text
        for macro_name in IGNORED_MACROS:
            pattern = re.compile(
                rf"<ac:structured-macro[^>]*ac:name=\"{re.escape(macro_name)}\"[^>]*>.*?</ac:structured-macro>",
                re.DOTALL | re.IGNORECASE,
            )
            output = pattern.sub("", output)
        return output

    def _remove_page_properties_report_macro(self, text: str) -> str:
        """Entfernt page-properties-report-Makros, Inhalt wird separat über Tabellen verarbeitet."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"page-properties-report\"[^>]*>.*?</ac:structured-macro>",
            re.DOTALL,
        )
        return pattern.sub("", text)

    def _replace_plantuml_macro(self, text: str, warnings: list[TransformWarning]) -> str:
        """Rendert PlantUML-Makros als fenced code block."""
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"(?:plantuml|plantumlrender)\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            body_match = re.search(r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>", block, re.DOTALL)
            if not body_match:
                warnings.append(
                    TransformWarning(
                        code="degraded_macro_rendering",
                        message="PlantUML-Makro ohne lesbaren CDATA-Body erkannt.",
                        context="plantuml",
                    )
                )
                return "\n[PLANTUML_BLOCK]\nPlantUML-Inhalt konnte nicht extrahiert werden.\n"
            return f"\n```plantuml\n{body_match.group(1).strip()}\n```\n"

        return pattern.sub(repl, text)

    def _unwrap_table_like_macro(self, text: str, macro_name: str) -> str:
        """Entfernt Wrapper-Makros um Tabellen und lässt den Rich-Text-Inhalt stehen."""
        return self._unwrap_macro_content(text, macro_name, rich_text_only=True)

    def _unwrap_macro_content(self, text: str, macro_name: str, *, rich_text_only: bool = False) -> str:
        """Entfernt Wrapper-Makros und behält – je nach Makro – den relevanten Inhalt bei."""
        pattern = re.compile(
            rf"<ac:structured-macro[^>]*ac:name=\"{re.escape(macro_name)}\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            body_match = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", block, re.DOTALL)
            if body_match:
                return body_match.group(1)

            if rich_text_only:
                return ""

            plain_body_match = re.search(r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>", block, re.DOTALL)
            if plain_body_match:
                return plain_body_match.group(1)
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
            return value

        return pattern.sub(repl, text)

    def _replace_task_items(self, text: str) -> str:
        """Extract, classify and render Confluence tasks as explicit open/completed sections."""
        all_tasks: list[ConfluenceTaskItem] = []

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            parsed = [self._parse_task_item(task_block) for task_block in TASK_ITEM_PATTERN.findall(block)]
            all_tasks.extend(parsed)
            return "\n"

        transformed = TASK_LIST_PATTERN.sub(repl, text)
        if not all_tasks:
            return transformed

        kept_tasks = [task for task in all_tasks if not task.drop_reason]
        dropped = [task for task in all_tasks if task.drop_reason]
        open_tasks = [task for task in kept_tasks if task.status == "open"]
        completed_tasks = [task for task in kept_tasks if task.status == "completed"]
        short_informative_kept = sum(1 for task in kept_tasks if len(task.cleaned_text) < 50)
        drop_stats = Counter(task.drop_reason for task in dropped)
        logger.debug(
            "Confluence tasks parsed=%s open=%s completed=%s kept=%s dropped=%s short_informative_kept=%s drop_reasons=%s",
            len(all_tasks),
            sum(1 for task in all_tasks if task.status == "open"),
            sum(1 for task in all_tasks if task.status == "completed"),
            len(kept_tasks),
            len(dropped),
            short_informative_kept,
            dict(drop_stats.most_common(5)),
        )

        rendered_sections: list[str] = []
        if open_tasks:
            rendered_sections.append("## Open Tasks\n\n" + "\n".join(self._render_task_item(task) for task in open_tasks))
        if completed_tasks:
            rendered_sections.append("## Completed Tasks\n\n" + "\n".join(self._render_task_item(task) for task in completed_tasks))
        if not rendered_sections:
            return transformed
        return transformed.rstrip() + "\n\n" + "\n\n".join(rendered_sections) + "\n"

    def _parse_task_item(self, task_block: str) -> ConfluenceTaskItem:
        """Parse one Confluence task XML block and return normalized task metadata."""
        status_raw = self._extract_xml_value(task_block, "ac:task-status").lower()
        status = "completed" if status_raw == "complete" else "open"
        body_raw = self._extract_xml_value(task_block, "ac:task-body")
        mentions = self._extract_mentions(body_raw)
        links = self._extract_links(body_raw)
        due_date = self._extract_due_date(body_raw)
        raw_text = self._html_to_text(body_raw)
        cleaned_text = self._clean_task_text(raw_text, mentions)
        contains_decision = self._contains_any(cleaned_text, DECISION_SIGNALS)
        contains_domain = self._contains_any(cleaned_text, DOMAIN_SIGNALS)

        task = ConfluenceTaskItem(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            status=status,
            assignees=mentions,
            links=links,
            due_date=due_date,
            contains_decision_signal=contains_decision,
            contains_domain_signal=contains_domain,
        )
        keep_reason, drop_reason = self._classify_task(task)
        task.keep_reason = keep_reason
        task.drop_reason = drop_reason
        return task

    def _extract_xml_value(self, block: str, tag: str) -> str:
        match = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", block, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else ""

    def _extract_mentions(self, body: str) -> list[str]:
        """Extract user mentions/assignees from Confluence user tags."""
        names = [name.strip() for name in MENTION_PATTERN.findall(body) if name.strip()]
        deduped: list[str] = []
        for name in names:
            if name not in deduped:
                deduped.append(name)
        return deduped

    def _extract_links(self, body: str) -> list[str]:
        links: list[str] = []
        for pattern in URL_PATTERNS:
            for match in re.finditer(pattern, body, re.DOTALL | re.IGNORECASE):
                url = match.group(1).strip()
                if url and url not in links:
                    links.append(url)
        return links

    def _extract_due_date(self, body: str) -> str | None:
        text = self._html_to_text(body)
        match = DUE_DATE_PATTERN.search(text)
        return match.group(1) if match else None

    def _html_to_text(self, value: str) -> str:
        normalized = re.sub(r'<ri:user[^>]*ri:display-name="([^"]+)"[^>]*/?>', r'@\1', value, flags=re.IGNORECASE)
        normalized = re.sub(r"<br\s*/?>", " ", normalized, flags=re.IGNORECASE)
        stripped = re.sub(r"<[^>]+>", " ", normalized)
        return re.sub(r"\s+", " ", html.unescape(stripped)).strip()

    def _clean_task_text(self, raw_text: str, mentions: list[str]) -> str:
        text = raw_text.strip()
        for mention in mentions:
            text = re.sub(rf"^@?{re.escape(mention)}[,:\s-]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:@\w+[,:\s-]*)+", "", text)
        text = re.sub(r"\s+", " ", text).strip(" .-")
        return text

    def _contains_any(self, text: str, terms: set[str]) -> bool:
        lower = text.lower()
        return any(term in lower for term in terms)

    def _is_semantically_trivial(self, cleaned_text: str) -> bool:
        normalized = re.sub(r"[.!]+$", "", cleaned_text.lower()).strip()
        return normalized in TRIVIAL_TASK_TERMS

    def _has_meaningful_statement(self, cleaned_text: str) -> bool:
        if not cleaned_text:
            return False
        words = [w for w in re.split(r"\s+", cleaned_text) if w]
        if len(words) >= 3:
            return True
        return bool(re.search(r"\d", cleaned_text) or re.search(r"[A-Z][a-z]+", cleaned_text))

    def _classify_task(self, task: ConfluenceTaskItem) -> tuple[str, str]:
        """Classify tasks using semantic signals instead of hard minimum length thresholds."""
        if not task.assignees:
            return "", "missing_mention"
        if not task.cleaned_text:
            return "", "empty_after_cleanup"
        if self._is_semantically_trivial(task.cleaned_text):
            return "", "trivial_communication"

        if task.links:
            return "has_link", ""
        if task.due_date:
            return "has_due_date", ""
        if task.contains_decision_signal:
            return "decision_signal", ""
        if task.contains_domain_signal:
            return "domain_signal", ""
        if task.assignees and self._has_meaningful_statement(task.cleaned_text):
            return "assignee_with_statement", ""
        if self._has_meaningful_statement(task.cleaned_text):
            return "meaningful_statement", ""

        return "", "insufficient_signal"

    def _render_task_item(self, task: ConfluenceTaskItem) -> str:
        lines = [f"- {task.cleaned_text}."]
        if task.assignees:
            lines.append(f"  Mentions: {', '.join(task.assignees)}.")
        lines.append(f"  Status: {task.status}.")
        if task.due_date:
            lines.append(f"  Date: {task.due_date}.")
        if task.links:
            lines.append(f"  Links: {', '.join(task.links)}.")
        return "\n".join(lines)

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
        for pattern in URL_PATTERNS:
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

    def _is_supported_macro(self, macro_name: str) -> bool:
        normalized = self._normalize_macro_name(macro_name)
        supported = {self._normalize_macro_name(name) for name in (SUPPORTED_CALLOUTS | SUPPORTED_SIMPLE | IGNORED_MACROS)}
        return normalized in supported


    def _normalize_macro_name(self, macro_name: str) -> str:
        return macro_name.strip().lower()

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
