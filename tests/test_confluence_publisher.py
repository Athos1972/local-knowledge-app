from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from common.logging_setup import get_logger
from processing.publish.mapping_config import ConfluencePublishConfig
from processing.publish.path_resolver import PublishPathResolver
from processing.publish.publisher import ConfluencePublisher


class ConfluencePublisherTests(unittest.TestCase):
    def test_from_sources_prefers_publish_confluence_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "config").mkdir(parents=True, exist_ok=True)

            (root / "config" / "publish_confluence.toml").write_text(
                """
[publish.confluence]
input_root = "~/from_publish_file/staging"
output_root = "~/from_publish_file/domains"

[publish.confluence.space_map]
"~NBUBEV" = "from/publish-file"
""".strip(),
                encoding="utf-8",
            )
            (root / "config" / "app.toml").write_text(
                """
[publish.confluence]
input_root = "~/from_app_file/staging"
output_root = "~/from_app_file/domains"

[publish.confluence.space_map]
"~NBUBEV" = "from/app-file"
""".strip(),
                encoding="utf-8",
            )

            previous_cwd = Path.cwd()
            previous_env = os.environ.get("APP_CONFIG_FILE")
            try:
                os.environ["APP_CONFIG_FILE"] = str(root / "config" / "app.toml")
                os.chdir(root)
                config = ConfluencePublishConfig.from_sources()
            finally:
                os.chdir(previous_cwd)
                if previous_env is None:
                    os.environ.pop("APP_CONFIG_FILE", None)
                else:
                    os.environ["APP_CONFIG_FILE"] = previous_env

            self.assertEqual("from/publish-file", config.space_map.get("~NBUBEV"))
            self.assertIn("from_publish_file/domains", str(config.output_root))

    def test_resolve_mapped_and_unmapped_space(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = ConfluencePublishConfig(
                input_root=root / "staging",
                output_root=root / "domains",
                manifests_dir=root / "system",
                space_map={"~NBUBEV": "sap/customer/a/confluence"},
            )
            resolver = PublishPathResolver(config)

            mapped_file = config.input_root / "tenant" / "~NBUBEV" / "123__seite.md"
            mapped_file.parent.mkdir(parents=True, exist_ok=True)
            mapped_file.write_text("---\ntitle: \"A\"\nsource_type: \"confluence\"\nspace_key: \"~NBUBEV\"\npage_id: \"123\"\nlabels: []\nsource_url: \"x\"\n---\n", encoding="utf-8")

            publisher = ConfluencePublisher(config, get_logger("test_publisher"))
            doc = publisher._reader.read(mapped_file)
            target = resolver.resolve(doc)
            self.assertEqual("mapped", target.mapping_status)
            self.assertEqual(config.output_root / "sap/customer/a/confluence/123__seite.md", target.output_file)

            doc.metadata["space_key"] = "~UNKNOWN"
            target_unmapped = resolver.resolve(doc)
            self.assertEqual("unmapped", target_unmapped.mapping_status)
            self.assertIn("_unmapped/confluence/~UNKNOWN", target_unmapped.output_file.as_posix())

    def test_publish_adds_metadata_and_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_root = root / "staging" / "confluence"
            source_file = input_root / "tenant" / "~NBUBEV" / "123__seite.md"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(
                "---\n"
                "title: \"Seite\"\n"
                "source_type: \"confluence\"\n"
                "space_key: \"~NBUBEV\"\n"
                "page_id: \"123\"\n"
                "labels: [\"a\"]\n"
                "source_url: \"https://example\"\n"
                "---\n\n"
                "# Inhalt\n",
                encoding="utf-8",
            )

            config = ConfluencePublishConfig(
                input_root=input_root,
                output_root=root / "domains",
                manifests_dir=root / "system",
                space_map={"~NBUBEV": "sap/customers/x/projects/y/confluence"},
            )
            publisher = ConfluencePublisher(config, get_logger("test_publisher"))

            result = publisher.publish_file(source_file)

            self.assertEqual("published", result.status)
            self.assertIsNotNone(result.output_file)
            assert result.output_file is not None
            written = result.output_file.read_text(encoding="utf-8")
            self.assertIn('content_origin: "confluence"', written)
            self.assertIn('domain_path: "sap/customers/x/projects/y/confluence"', written)
            self.assertIn("# Inhalt", written)


if __name__ == "__main__":
    unittest.main()
