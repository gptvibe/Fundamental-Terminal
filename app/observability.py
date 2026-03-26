from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def emit_structured_log(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {"event": event}
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    logger.log(level, json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":")))


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)