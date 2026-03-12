from __future__ import annotations

import inspect
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from common.config import AppConfig

_ROOT_LOGGER_NAME = "local_knowledge_app"
_DEFAULT_RUN_ID = uuid.uuid4().hex[:8]
_CONFIGURED = False


class _RunIdFilter(logging.Filter):
    """Injects a run id into each log record."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


def get_logger(name: str | None = None, run_id: str | None = None) -> logging.Logger:
    """Return an app logger and configure handlers once."""
    _configure_once(run_id=run_id)

    logger_suffix = name or _detect_script_name()
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{logger_suffix}")


def _configure_once(run_id: str | None = None) -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    log_level_name = str(AppConfig.get("logging", "level", default="INFO")).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = AppConfig.get_path(None, "logging", "log_dir", default="logs")
    log_to_console = bool(AppConfig.get("logging", "log_to_console", default=True))
    log_to_file = bool(AppConfig.get("logging", "log_to_file", default=True))
    separate_file_per_run = bool(
        AppConfig.get("logging", "separate_file_per_run", default=True)
    )

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(log_level)
    root_logger.propagate = False

    if root_logger.handlers:
        _CONFIGURED = True
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | run=%(run_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    active_run_id = run_id or _DEFAULT_RUN_ID
    run_filter = _RunIdFilter(active_run_id)

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(run_filter)
        root_logger.addHandler(console_handler)

    if log_to_file:
        log_dir.mkdir(parents=True, exist_ok=True)

        script_name = _detect_script_name()
        if separate_file_per_run:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{script_name}_{timestamp}.log"
        else:
            file_name = f"{script_name}.log"

        file_handler = logging.FileHandler(log_dir / file_name, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(run_filter)
        root_logger.addHandler(file_handler)

    _CONFIGURED = True


def _detect_script_name() -> str:
    main_module = sys.modules.get("__main__")
    if main_module and hasattr(main_module, "__file__"):
        return Path(main_module.__file__).stem

    for frame_info in inspect.stack():
        module = inspect.getmodule(frame_info.frame)
        if module and getattr(module, "__file__", None):
            module_path = Path(module.__file__)
            if module_path.stem not in {"logging_setup", "config"}:
                return module_path.stem

    return "application"


class AppLogger:
    """Backward-compatible class facade around `get_logger`."""

    @classmethod
    def get_logger(cls) -> logging.Logger:
        return get_logger()
