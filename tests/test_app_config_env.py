from __future__ import annotations

from pathlib import Path

from common.config import AppConfig


def test_loads_dotenv_value_without_overriding_existing_env(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "ANYTHINGLLM_API_KEY=from_dotenv",
                "export ANYTHINGLLM_WORKSPACE=workspace_from_dotenv",
                "QUOTED_VALUE=\"quoted\"",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_ENV_FILE", str(env_file))
    monkeypatch.setenv("ANYTHINGLLM_WORKSPACE", "existing_workspace")

    AppConfig._env_loaded = False
    AppConfig._config = {}

    assert AppConfig.get_str("ANYTHINGLLM_API_KEY", default="") == "from_dotenv"
    assert AppConfig.get_str("ANYTHINGLLM_WORKSPACE", default="") == "existing_workspace"
    assert AppConfig.get_str("QUOTED_VALUE", default="") == "quoted"


def test_missing_dotenv_is_safe(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.env"
    monkeypatch.setenv("APP_ENV_FILE", str(missing))

    AppConfig._env_loaded = False
    AppConfig._config = {}

    assert AppConfig.get_str("UNSET_KEY", "anythingllm", "api_key", default="fallback") == "fallback"
