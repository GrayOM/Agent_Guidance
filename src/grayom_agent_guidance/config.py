import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def grayom_home() -> Path:
    return Path(os.environ.get("GRAYOM_HOME", Path.home() / ".grayom")).expanduser().resolve()


class DiscoveryConfig(BaseModel):
    github: bool = True


class CacheConfig(BaseModel):
    ttl_hours: int = Field(default=24, ge=1, le=720)


class UIConfig(BaseModel):
    verbose: bool = False


class GrayOMConfig(BaseModel):
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


def load_config(path: Path | None = None) -> GrayOMConfig:
    target = path or grayom_home() / "config.yaml"
    if not target.exists():
        return GrayOMConfig()
    value = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return GrayOMConfig.model_validate(value)
