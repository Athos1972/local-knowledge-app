"""Transformation von Confluence-Makros in Markdown-freundliche Darstellungen."""

from __future__ import annotations

import re

from processing.confluence.models import TransformWarning

SUPPORTED_CALLOUTS = {"info", "note", "warning", "tip", "panel"}
SUPPORTED_SIMPLE = {"expand", "status", "task-list"}


class MacroTransformer:
    """Konvertiert ausgewählte Confluence-Makros in MVP-Markdown."""

    def transform(self, text: str) -> tuple[str, list[TransformWarning], list[str]]:
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        transformed = text
        for macro in SUPPORTED_CALLOUTS:
            transformed = self._replace_callout_macro(transformed, macro)

        transformed = self._replace_expand_macro(transformed)
        transformed = self._replace_status_macro(transformed)
        transformed = self._replace_task_items(transformed)

        macro_pattern = re.compile(r"<ac:structured-macro[^>]*ac:name=\"([^\"]+)\"[^>]*>.*?</ac:structured-macro>", re.DOTALL)

        def replace_unsupported(match: re.Match[str]) -> str:
            macro_name = match.group(1).strip()
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
            return f"\n[UNSUPPORTED_MACRO: {macro_name}]\n"

        transformed = macro_pattern.sub(replace_unsupported, transformed)
        return transformed, warnings, unsupported

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

    def _replace_expand_macro(self, text: str) -> str:
        pattern = re.compile(
            r"<ac:structured-macro[^>]*ac:name=\"expand\"[^>]*>(.*?)</ac:structured-macro>",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            block = match.group(1)
            title_match = re.search(r"<ac:parameter[^>]*ac:name=\"title\"[^>]*>(.*?)</ac:parameter>", block, re.DOTALL)
            title = self._strip_tags(title_match.group(1)).strip() if title_match else "Details"
            body_match = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", block, re.DOTALL)
            body = self._strip_tags(body_match.group(1)).strip() if body_match else ""
            return f"\n**Expand: {title}**\n\n{body}\n"

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
