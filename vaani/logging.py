"""Structured JSON logging with trace IDs (call_id flows as trace_id)."""

from __future__ import annotations

import json
import logging
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "trace_id": getattr(record, "trace_id", None),
            }
        )


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            handler.setLevel(level)
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)
    root.addHandler(handler)
    root.setLevel(level)


def bind(trace_id: str, **fields: object) -> dict[str, object]:
    """Build the `extra` dict for trace-correlated log lines."""
    return {"trace_id": trace_id, **fields}
