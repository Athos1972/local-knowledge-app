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


def test_get_path_expands_tilde_from_config(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True)
    config_path = tmp_path / "app.toml"
    config_path.write_text('[paths]\nroot = "~/data-root"\n', encoding="utf-8")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_path))

    AppConfig._env_loaded = False
    AppConfig._config = None

    resolved = AppConfig.get_path(None, "paths", "root", default="~/fallback")
    assert resolved == fake_home / "data-root"


def test_app_config_file_supports_tilde(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home2"
    fake_home.mkdir(parents=True)
    cfg = fake_home / "cfg.toml"
    cfg.write_text('[x]\nvalue = "ok"\n', encoding="utf-8")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("APP_CONFIG_FILE", "~/cfg.toml")

    AppConfig._env_loaded = False
    AppConfig._config = None

    assert AppConfig.get("x", "value", default="") == "ok"
