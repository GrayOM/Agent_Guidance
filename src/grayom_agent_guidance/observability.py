import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import grayom_home


SECRET_KEY = re.compile(r"(?i)(token|password|secret|api[_-]?key|authorization|credential)")
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")


def redact(value: Any, key: str | None = None) -> Any:
    if key and SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return BEARER.sub("Bearer [REDACTED]", value)
    return value


class EventLogger:
    def __init__(self, path: Path | None = None, verbose: bool = False) -> None:
        self.path = path or grayom_home() / "logs" / "grayom.jsonl"
        self.verbose = verbose

    def write(self, event: str, **fields: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = redact({
            "timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields,
        })
        # Open with 0o600 so the log is never briefly world-readable between create and chmod.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        if self.verbose:
            logging.getLogger("grayom").info("%s %s", event, redact(fields))
