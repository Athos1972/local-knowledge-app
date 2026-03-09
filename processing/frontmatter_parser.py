# processing/frontmatter_parser.py

import yaml
import re


class FrontmatterParser:
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        re.DOTALL
    )

    @classmethod
    def parse(cls, text: str):
        """
        Extrahiert YAML-Frontmatter aus Markdown.

        Returns:
            metadata (dict)
            cleaned_text (str)
        """

        match = cls.FRONTMATTER_PATTERN.match(text)

        if not match:
            return {}, text

        yaml_block = match.group(1)
        body = match.group(2)

        try:
            metadata = yaml.safe_load(yaml_block) or {}
        except Exception:
            metadata = {}

        return metadata, body