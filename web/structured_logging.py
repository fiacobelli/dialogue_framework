"""Small JSON logging helper for operational events."""

from __future__ import annotations

import json
import logging
from typing import Any


def _safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif isinstance(value, (list, tuple, set)):
            safe[key] = list(value)
        elif isinstance(value, dict):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Write one structured JSON log line."""
    payload = {'event': event, **_safe_fields(fields)}
    logger.log(level, json.dumps(payload, sort_keys=True))
