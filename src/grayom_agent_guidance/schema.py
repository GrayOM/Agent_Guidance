import json
from pathlib import Path
from typing import Any

from .errors import ConfigurationError


CURRENT_SCHEMA_VERSION = 1


def load_versioned_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"versioned document must be an object: {path}")
    version = value.get("schema_version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"invalid schema version in {path}")
    if version > CURRENT_SCHEMA_VERSION:
        raise ConfigurationError(
            "This GrayOM data was written by a newer version.",
            technical_message=f"unsupported schema_version {version} in {path}",
            recoverable=False,
            suggested_action="Upgrade GrayOM before modifying this data.",
        )
    return value
