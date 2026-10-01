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


class SkillsConfig(BaseModel):
    # None keeps the per-mode default: an Agent loads every installed Skill's description,
    # so the cap is what stops a large repository from spending the user's context.
    max_per_component: int | None = Field(default=None, ge=1, le=100)


class GrayOMConfig(BaseModel):
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)


def load_config(path: Path | None = None) -> GrayOMConfig:
    target = path or grayom_home() / "config.yaml"
    if not target.exists():
        return GrayOMConfig()
    value = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return GrayOMConfig.model_validate(value)
