from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class AgentType(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"


class AgentInstallation(BaseModel):
    agent: AgentType
    detected: bool
    executable: Path | None = None
    config_path: Path | None = None
    version: str | None = None
    details: dict[str, str] = Field(default_factory=dict)

