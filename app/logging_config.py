
import json
import logging
import os
from logging import Handler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

DEFAULT_RECORD_ATTRS = {
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 'module',
    'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName', 'created', 'msecs',
    'relativeCreated', 'thread', 'threadName', 'processName', 'process', 'message'
}


def _stringify(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            'time': self.formatTime(record, datefmt='%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in DEFAULT_RECORD_ATTRS and not key.startswith('_')
        }
        for key, value in extras.items():
            base[key] = _stringify(value)

        if record.exc_info:
            base['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(base, ensure_ascii=False)


def _ensure_logs_dir() -> Path:
    logs_dir = Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _configure_handler(handler: Handler, level: int) -> Handler:
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    return handler


def setup_logging(level_env: str | None = None) -> None:
    level_name = (level_env or os.getenv('LOG_LEVEL', 'INFO')).upper()
    level = getattr(logging, level_name, logging.INFO)
    logs_dir = _ensure_logs_dir()

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)

    console = _configure_handler(logging.StreamHandler(), level)
    root.addHandler(console)

    app_file_handler = _configure_handler(
        TimedRotatingFileHandler(
            filename=str(logs_dir / 'instasave.log'),
            when='midnight', backupCount=7, encoding='utf-8'
        ),
        level,
    )
    root.addHandler(app_file_handler)

    scraper_logger = logging.getLogger('instasave.scraper')
    scraper_logger.setLevel(level)
    for handler in list(scraper_logger.handlers):
        if isinstance(handler, TimedRotatingFileHandler):
            scraper_logger.removeHandler(handler)
            handler.close()

    scraper_file_handler = _configure_handler(
        TimedRotatingFileHandler(
            filename=str(logs_dir / 'scraper.log'),
            when='midnight', backupCount=7, encoding='utf-8'
        ),
        level,
    )
    scraper_logger.addHandler(scraper_file_handler)

    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
