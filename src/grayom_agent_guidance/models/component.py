from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl

from .agent import AgentType
from .capability import Capability


class ComponentType(StrEnum):
    SKILL = "skill"
    MCP = "mcp"
    PLUGIN = "plugin"


class Permission(StrEnum):
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    NETWORK = "network"
    SHELL = "shell"
    SUBPROCESS = "subprocess"
    CREDENTIALS = "credentials"
    REPOSITORY_WRITE = "repository_write"
    DESTRUCTIVE = "destructive"


class Compatibility(BaseModel):
    agents: set[AgentType]
    notes: str | None = None


class Component(BaseModel):
    id: str
    name: str
    type: ComponentType
    source_url: HttpUrl
    official: bool = False
    capabilities: set[Capability] = Field(default_factory=set)
    compatibility: Compatibility
    permissions: set[Permission] = Field(default_factory=set)
    tool_names: set[str] = Field(default_factory=set)
    config_targets: set[str] = Field(default_factory=set)
    context_cost: int = Field(default=1, ge=1, le=5)
    quality_score: int = Field(default=50, ge=0, le=100)
    install_command: list[str] | None = None
    included_components: set[str] = Field(default_factory=set)

