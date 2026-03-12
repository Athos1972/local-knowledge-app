from __future__ import annotations

from pipelines.domain_mapping import (
    MappingConfig,
    MappingRule,
    choose_mapping_rule,
    derive_title_from_filename,
)


def test_choose_mapping_rule_prefix_and_fallback() -> None:
    config = MappingConfig(
        default_target_subpath="external/unassigned",
        rules=[
            MappingRule(id="wstw", path_prefix="wstw/", target_subpath="external/wstw"),
        ],
    )

    matched = choose_mapping_rule(config, relative_source_path="wstw/path/file.pdf", file_name="file.pdf")
    assert matched.id == "wstw"

    fallback = choose_mapping_rule(config, relative_source_path="other/path/file.pdf", file_name="file.pdf")
    assert fallback.id == "default"
    assert fallback.target_subpath == "external/unassigned"


def test_derive_title_from_filename() -> None:
    assert derive_title_from_filename("my_test-file-name.pdf") == "my test file name"
