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

    @classmethod
    def load(cls) -> dict[str, Any]:
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
        env_value = os.getenv(env_key)
        if env_value is not None and env_value.strip():
            return env_value.strip()

        value = cls.get(*keys, default=default)
        return str(value).strip() if value is not None else default
