from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


class AppConfig:
    _config: dict[str, Any] | None = None
    _env_loaded = False

    @classmethod
    def _load_dotenv_once(cls) -> None:
        """Lädt optional eine lokale .env-Datei ohne bestehende ENV-Werte zu überschreiben."""
        if cls._env_loaded:
            return

        env_file = os.getenv("APP_ENV_FILE", ".env")
        env_path = Path(env_file)
        if not env_path.exists():
            cls._env_loaded = True
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export ") :].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]

            os.environ.setdefault(key, value)

        cls._env_loaded = True

    @classmethod
    def load(cls) -> dict[str, Any]:
        cls._load_dotenv_once()

        if cls._config is not None:
            return cls._config

        config_file = os.getenv("APP_CONFIG_FILE", "config/app.toml")
        path = Path(config_file)

        if not path.exists():
            cls._config = {}
            return cls._config

        with path.open("rb") as f:
            cls._config = tomllib.load(f)

        return cls._config

    @classmethod
    def get(cls, *keys: str, default: Any = None) -> Any:
        data = cls.load()
        current: Any = data

        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]

        return current

    @classmethod
    def get_str(cls, env_key: str, *keys: str, default: str) -> str:
        """Read string config with ENV override precedence."""
        cls._load_dotenv_once()

        env_value = os.getenv(env_key)
        if env_value is not None and env_value.strip():
            return env_value.strip()

        value = cls.get(*keys, default=default)
        return str(value).strip() if value is not None else default
