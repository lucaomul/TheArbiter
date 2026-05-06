import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - optional pretty console path
    from rich.logging import RichHandler
except ImportError:  # pragma: no cover - optional dependency
    RichHandler = None


_CONFIGURED = False


class _DefaultContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = ""
        if not hasattr(record, "iteration"):
            record.iteration = None
        if not hasattr(record, "agent_name"):
            record.agent_name = ""
        if not hasattr(record, "provider"):
            record.provider = ""
        if not hasattr(record, "model"):
            record.model = ""
        if not hasattr(record, "latency_ms"):
            record.latency_ms = None
        if not hasattr(record, "score"):
            record.score = None
        return True


class _JsonFormatter(logging.Formatter):
    RESERVED = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "run_id": getattr(record, "run_id", "") or "",
            "iteration": getattr(record, "iteration", None),
            "agent_name": getattr(record, "agent_name", "") or "",
        }
        for key, value in record.__dict__.items():
            if key in self.RESERVED or key.startswith("_"):
                continue
            if key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"[{record.levelname}] {record.getMessage()}"
        extras = []
        for key in ("run_id", "iteration", "agent_name", "provider", "model", "latency_ms", "score"):
            value = getattr(record, key, None)
            if value in ("", None):
                continue
            extras.append(f"{key}={value}")
        if extras:
            base += " | " + " ".join(extras)
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = str(os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = str(os.getenv("LOG_FORMAT", "console")).lower()

    handler: logging.Handler
    if log_format == "json":
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
    else:
        if RichHandler is not None:
            handler = RichHandler(rich_tracebacks=True, show_time=False, show_path=False)
        else:
            handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ConsoleFormatter())

    handler.addFilter(_DefaultContextFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    logger.addFilter(_DefaultContextFilter())
    return logger
