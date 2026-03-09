from __future__ import annotations

import inspect
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from common.config import AppConfig


class _RunIdFilter(logging.Filter):
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


class AppLogger:
    _configured = False
    _run_id = uuid.uuid4().hex[:8]
    _root_logger_name = "local_knowledge_app"

    @classmethod
    def get_logger(cls) -> logging.Logger:
        cls._configure_once()
        script_name = cls._detect_script_name()
        logger_name = f"{cls._root_logger_name}.{script_name}"
        return logging.getLogger(logger_name)

    @classmethod
    def _configure_once(cls) -> None:
        if cls._configured:
            return

        log_level_name = str(AppConfig.get("logging", "level", default="INFO")).upper()
        log_level = getattr(logging, log_level_name, logging.INFO)

        log_dir = Path(AppConfig.get("logging", "log_dir", default="logs"))
        log_to_console = bool(AppConfig.get("logging", "log_to_console", default=True))
        log_to_file = bool(AppConfig.get("logging", "log_to_file", default=True))
        separate_file_per_run = bool(
            AppConfig.get("logging", "separate_file_per_run", default=True)
        )

        root_logger = logging.getLogger(cls._root_logger_name)
        root_logger.setLevel(log_level)
        root_logger.propagate = False

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | run=%(run_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        run_filter = _RunIdFilter(cls._run_id)

        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            console_handler.addFilter(run_filter)
            root_logger.addHandler(console_handler)

        if log_to_file:
            log_dir.mkdir(parents=True, exist_ok=True)

            script_name = cls._detect_script_name()
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

        cls._configured = True

    @classmethod
    def _detect_script_name(cls) -> str:
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