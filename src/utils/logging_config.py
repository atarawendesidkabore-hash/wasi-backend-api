"""
Structured JSON logging for production; human-readable text for dev.

Uses the existing request_id ContextVar from src.middleware.request_id
so every log line in a request context carries the correlation ID.
"""
import json
import logging
import sys
from datetime import datetime, timezone


def _get_request_id() -> str:
    """Safely import and read request_id_var without circular imports."""
    try:
        from src.middleware.request_id import request_id_var
        return request_id_var.get()
    except Exception:
        return ""


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line — parseable by CloudWatch, Datadog, ELK."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _get_request_id(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(*, debug: bool = False):
    """
    Configure root logger.
    - debug=True  → human-readable text format (local dev)
    - debug=False → JSON format (production / log aggregators)
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove any existing handlers (e.g. from basicConfig)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    if debug:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
    else:
        handler.setFormatter(JSONFormatter())

    root.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
