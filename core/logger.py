from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"

_CONFIGURED = False


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "service_name": getattr(record, "service_name", record.name),
            "log_level": record.levelname,
            "job_id": getattr(record, "job_id", None),
            "message": record.getMessage(),
        }

        for key in (
            "job_type",
            "state",
            "progress",
            "model_name",
            "device",
            "context",
            "elapsed_seconds",
            "vram_allocated_mb",
            "vram_reserved_mb",
            "vram_peak_allocated_mb",
            "transcript_json_path",
            "transcript_text_path",
            "segment_count",
            "audio_path",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["stack_trace"] = "".join(traceback.format_exception(*record.exc_info)).rstrip()

        return json.dumps(payload, default=str, ensure_ascii=False)


class JobLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = JsonLogFormatter()

    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    _CONFIGURED = True


def get_logger(service_name: str, job_id: str | None = None) -> JobLoggerAdapter:
    configure_logging()
    return JobLoggerAdapter(
        logging.getLogger(service_name),
        {"service_name": service_name, "job_id": job_id},
    )
