from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_run_transform_confluence_skips_log_year_titles(tmp_path: Path) -> None:
    input_root = tmp_path / "exports" / "confluence"
    page_dir = input_root / "inst-a" / "spaces" / "DOC" / "by-id" / "123"
    page_dir.mkdir(parents=True)
    (page_dir / "metadata.json").write_text(
        json.dumps({"id": "123", "title": "Log 2024 Deployment", "space_key": "DOC"}),
        encoding="utf-8",
    )
    (page_dir / "content.storage.xml").write_text("<p>Soll ignoriert werden</p>", encoding="utf-8")

    output_root = tmp_path / "staging" / "confluence"
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    cmd = [
        sys.executable,
        "scripts/run_transform_confluence.py",
        "--input-root",
        str(input_root),
        "--output-root",
        str(output_root),
        "--run-id",
        "confluence-test-run",
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not output_root.exists() or not any(output_root.rglob("*.md"))


def test_main_finalizes_terminology_report_once(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_confluence as module
    from processing.confluence.models import ConfluenceRawPage

    class DummyLoader:
        def __init__(self, _input_root: Path) -> None:
            pass

        def load_pages(self, space_filter: str | None = None):
            yield ConfluenceRawPage(
                page_id="1",
                title="Page 1",
                space_key="DOC",
                body="A" * 500,
                source_ref="doc-1.xml",
                source_url="https://example.invalid/1",
                labels=[],
                attachments=[],
            )
            yield ConfluenceRawPage(
                page_id="2",
                title="Page 2",
                space_key="DOC",
                body="B" * 500,
                source_ref="doc-2.xml",
                source_url="https://example.invalid/2",
                labels=[],
                attachments=[],
            )

    class DummyTransformer:
        instances: list["DummyTransformer"] = []

        def __init__(self) -> None:
            self.transform_calls = 0
            self.finalize_calls = 0
            DummyTransformer.instances.append(self)

        def should_ignore_page(self, page) -> bool:  # noqa: ANN001
            return False

        def transform(self, page):  # noqa: ANN001
            self.transform_calls += 1
            from processing.confluence.models import ConfluenceTransformedPage

            return ConfluenceTransformedPage(
                page_id=page.page_id,
                space_key=page.space_key,
                title=page.title,
                body_markdown=f"# {page.title}\n\n{page.body}",
                source_ref=page.source_ref,
                source_url=page.source_url,
            )

        def finalize_terminology_report(self) -> Path:
            self.finalize_calls += 1
            report_path = tmp_path / "reports" / "terminology_candidates.csv"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("source_type,term,count\nconfluence,ALPHA,2\n", encoding="utf-8")
            return report_path

    monkeypatch.setattr(module, "ConfluenceExportLoader", DummyLoader)
    monkeypatch.setattr(module, "ConfluenceTransformer", DummyTransformer)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-test")

    input_root = tmp_path / "exports" / "confluence"
    output_root = tmp_path / "staging" / "confluence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transform_confluence.py",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--run-id",
            "run-test",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    assert DummyTransformer.instances
    transformer = DummyTransformer.instances[0]
    assert transformer.transform_calls == 2
    assert transformer.finalize_calls == 1


def test_main_finalizes_terminology_report_with_zero_pages(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_confluence as module

    class EmptyLoader:
        def __init__(self, _input_root: Path) -> None:
            pass

        def load_pages(self, space_filter: str | None = None):
            return iter(())

    class DummyTransformer:
        instances: list["DummyTransformer"] = []

        def __init__(self) -> None:
            self.finalize_calls = 0
            DummyTransformer.instances.append(self)

        def should_ignore_page(self, page) -> bool:  # noqa: ANN001
            return False

        def transform(self, page):  # noqa: ANN001
            raise AssertionError("should not be called for empty loader")

        def finalize_terminology_report(self):
            self.finalize_calls += 1
            return None

    monkeypatch.setattr(module, "ConfluenceExportLoader", EmptyLoader)
    monkeypatch.setattr(module, "ConfluenceTransformer", DummyTransformer)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-empty")

    input_root = tmp_path / "exports" / "confluence"
    output_root = tmp_path / "staging" / "confluence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transform_confluence.py",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--run-id",
            "run-empty",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    assert DummyTransformer.instances
    assert DummyTransformer.instances[0].finalize_calls == 1


def test_main_skips_writing_final_markdown_below_min_chars(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_confluence as module
    from processing.confluence.models import ConfluenceRawPage

    class OnePageLoader:
        def __init__(self, _input_root: Path) -> None:
            pass

        def load_pages(self, space_filter: str | None = None):
            yield ConfluenceRawPage(
                page_id="1",
                title="Kurzseite",
                space_key="DOC",
                body="A" * 500,
                source_ref="doc-1.xml",
                source_url="https://example.invalid/1",
                labels=[],
                attachments=[],
            )

    class DummyTransformer:
        def should_ignore_page(self, page) -> bool:  # noqa: ANN001
            return False

        def transform(self, page):  # noqa: ANN001
            from processing.confluence.models import ConfluenceTransformedPage

            return ConfluenceTransformedPage(
                page_id=page.page_id,
                space_key=page.space_key,
                title=page.title,
                body_markdown="kurz",
                source_ref=page.source_ref,
                source_url=page.source_url,
            )

        def finalize_terminology_report(self):
            return None

    monkeypatch.setattr(module, "ConfluenceExportLoader", OnePageLoader)
    monkeypatch.setattr(module, "ConfluenceTransformer", DummyTransformer)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-small")

    config_path = tmp_path / "app.toml"
    config_path.write_text(
        """
[confluence_transform]
minimum_number_of_raw_characters_in_page = 0
minimum_count_characters_confluence_final_page = 200
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_path))
    module.AppConfig._config = None

    input_root = tmp_path / "exports" / "confluence"
    output_root = tmp_path / "staging" / "confluence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transform_confluence.py",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--run-id",
            "run-small",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    assert not output_root.exists() or not any(output_root.rglob("*.md"))


def test_main_writes_page_below_min_chars_when_complex_table_exists(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_confluence as module
    from processing.confluence.models import ConfluenceRawPage

    class OnePageLoader:
        def __init__(self, _input_root: Path) -> None:
            pass

        def load_pages(self, space_filter: str | None = None):
            yield ConfluenceRawPage(
                page_id="1",
                title="Kurzseite mit Tabelle",
                space_key="DOC",
                body="A" * 500,
                source_ref="doc-1.xml",
                source_url="https://example.invalid/1",
                labels=[],
                attachments=[],
            )

    class DummyTransformer:
        def should_ignore_page(self, page) -> bool:  # noqa: ANN001
            return False

        def transform(self, page):  # noqa: ANN001
            from processing.confluence.models import ConfluenceExtraDocument, ConfluenceTransformedPage

            return ConfluenceTransformedPage(
                page_id=page.page_id,
                space_key=page.space_key,
                title=page.title,
                body_markdown="kurz",
                source_ref=page.source_ref,
                source_url=page.source_url,
                extra_documents=[
                    ConfluenceExtraDocument(
                        file_name="1__kurzseite-mit-tabelle__table_01.md",
                        title="Tabelle",
                        doc_type="confluence_table",
                        body_markdown="Inhalt",
                    )
                ],
            )

        def finalize_terminology_report(self):
            return None

    monkeypatch.setattr(module, "ConfluenceExportLoader", OnePageLoader)
    monkeypatch.setattr(module, "ConfluenceTransformer", DummyTransformer)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-small-table")

    config_path = tmp_path / "app.toml"
    config_path.write_text(
        """
[confluence_transform]
minimum_number_of_raw_characters_in_page = 0
minimum_count_characters_confluence_final_page = 200
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_path))
    module.AppConfig._config = None

    input_root = tmp_path / "exports" / "confluence"
    output_root = tmp_path / "staging" / "confluence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transform_confluence.py",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--run-id",
            "run-small-table",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    md_files = list(output_root.rglob("*.md"))
    assert len(md_files) == 2
