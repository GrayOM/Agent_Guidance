import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# Where state lived before the project was renamed. The author is GrayOM; the project is
# Agent Guidance, and the two had been conflated in every identifier.
LEGACY_HOME = ".grayom"


def agent_guidance_home() -> Path:
    return Path(
        os.environ.get("AGENT_GUIDANCE_HOME", Path.home() / ".agent-guidance")
    ).expanduser().resolve()


def legacy_home() -> Path | None:
    """The pre-rename state directory, when it is still on disk and the new one is not.

    Nothing is moved: that directory records what was installed into the user's Agents, and
    relocating it on their behalf, silently, is not this program's call. Returning it lets the
    CLI say where the old records went, so an upgrade does not look like an empty slate.
    """
    if os.environ.get("AGENT_GUIDANCE_HOME"):
        return None
    legacy = Path.home() / LEGACY_HOME
    return legacy if legacy.is_dir() and not agent_guidance_home().exists() else None


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


class AgentGuidanceConfig(BaseModel):
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)


def load_config(path: Path | None = None) -> AgentGuidanceConfig:
    target = path or agent_guidance_home() / "config.yaml"
    if not target.exists():
        return AgentGuidanceConfig()
    value = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return AgentGuidanceConfig.model_validate(value)
