from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator

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
    EXTERNAL_DOWNLOAD = "external_download"
    FILESYSTEM_DELETE = "filesystem_delete"


class InstallKind(StrEnum):
    NONE = "none"
    GIT_SKILLS = "git_skills"
    MCP_HTTP = "mcp_http"
    MCP_STDIO = "mcp_stdio"
    PLUGIN_GIT = "plugin_git"
    # A Claude Code plugin is installed from a marketplace, which is the only path that
    # fetches it, validates its manifest and can be undone by an inverse command.
    PLUGIN_MARKETPLACE = "plugin_marketplace"


class SourceType(StrEnum):
    OFFICIAL = "official"
    GITHUB = "github"
    REGISTRY = "registry"
    CACHE = "cache"


class MaintenanceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class CandidateState(StrEnum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"


class EvidenceItem(BaseModel):
    field: str
    value: Any
    source: str
    location: str | None = None


class TrustMetadata(BaseModel):
    source_type: SourceType = SourceType.REGISTRY
    official: bool = False
    verified: bool = False
    verification_reason: str = "local registry entry"


class DependencyRequirement(BaseModel):
    name: str
    executable: str
    required: bool = True
    detected: bool | None = None
    evidence: str | None = None


class InstallMethod(BaseModel):
    kind: InstallKind = InstallKind.NONE
    repository: HttpUrl | None = None
    ref: str | None = None
    subpaths: list[str] = Field(default_factory=list)
    url: HttpUrl | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    env_vars: list[str] = Field(default_factory=list)
    bearer_token_env_var: str | None = None
    startup_timeout_sec: float = Field(default=10, gt=0, le=120)
    # A plugin is addressed as "<plugin>@<marketplace>"; marketplace_source is where the
    # marketplace is added from when the Agent does not already know it.
    plugin_id: str | None = None
    marketplace: str | None = None
    marketplace_source: str | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> "InstallMethod":
        if self.kind in {InstallKind.GIT_SKILLS, InstallKind.PLUGIN_GIT} and not self.repository:
            raise ValueError("git installation requires repository")
        if self.kind == InstallKind.MCP_HTTP and not self.url:
            raise ValueError("HTTP MCP installation requires url")
        if self.kind == InstallKind.MCP_STDIO and not self.command:
            raise ValueError("stdio MCP installation requires command")
        if self.kind == InstallKind.PLUGIN_MARKETPLACE:
            if not self.plugin_id or "@" not in self.plugin_id:
                raise ValueError("marketplace plugin installation requires plugin@marketplace")
            if not self.marketplace:
                self.marketplace = self.plugin_id.split("@", 1)[1]
        return self


class SkillSelectionPolicy(BaseModel):
    """Which Skills of a repository to install, and how many.

    A Skill repository can hold dozens of Skills, and an Agent loads every installed
    Skill's name and description into its context, so installing all of them spends the
    user's context on work they did not ask for. core decides the policy from the
    interview; the adapter applies it once the repository is on disk.
    """

    capabilities: set[Capability] = Field(default_factory=set)
    limit: int = Field(default=6, ge=1, le=100)


class SecurityMetadata(BaseModel):
    shell_execution: bool = False
    subprocess: bool = False
    external_download: bool = False
    network_access: bool = False
    filesystem_write: bool = False
    filesystem_delete: bool = False
    credential_access: bool = False
    repository_write: bool = False
    destructive_operations: bool = False
    install_script: bool = False
    update_script: bool = False


class MaintenanceMetadata(BaseModel):
    status: MaintenanceStatus = MaintenanceStatus.UNKNOWN
    last_verified: str | None = None
    license: str | None = None
    stars: int | None = Field(default=None, ge=0)
    forks: int | None = Field(default=None, ge=0)
    last_commit: str | None = None
    latest_release: str | None = None
    archived: bool = False
    issue_activity: str | None = None
    release_activity: str | None = None


class Compatibility(BaseModel):
    agents: set[AgentType]
    notes: str | None = None


class AgentRequirement(BaseModel):
    min_version: str | None = None
    evidence: str | None = None


COMPONENT_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"


class Component(BaseModel):
    # The id becomes a filesystem name in state/component manifests and managed asset roots,
    # so it must never carry a separator or a leading dot.
    id: str = Field(pattern=COMPONENT_ID_PATTERN, max_length=128)
    name: str
    type: ComponentType
    source: str = "local_registry"
    source_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    repository_url: HttpUrl | None = None
    official: bool = False
    capabilities: set[Capability] = Field(default_factory=set)
    supported_agents: set[AgentType] = Field(default_factory=set)
    agent_requirements: dict[AgentType, AgentRequirement] = Field(default_factory=dict)
    compatibility: Compatibility | None = None
    permissions: set[Permission] = Field(default_factory=set)
    tool_names: set[str] = Field(default_factory=set)
    config_targets: set[str] = Field(default_factory=set)
    context_cost: int = Field(default=1, ge=1, le=5)
    quality_score: int = Field(default=50, ge=0, le=100)
    install_command: list[str] | None = None
    included_components: set[str] = Field(default_factory=set)
    conflicts: set[str] = Field(default_factory=set)
    overlaps: set[str] = Field(default_factory=set)
    workflows: set[str] = Field(default_factory=set)
    install_paths: set[str] = Field(default_factory=set)
    config_keys: set[str] = Field(default_factory=set)
    install_method: InstallMethod = Field(default_factory=InstallMethod)
    # Set by the install Plan, not by discovery: it depends on what this run asked for.
    skill_selection: SkillSelectionPolicy | None = None
    security_metadata: SecurityMetadata = Field(default_factory=SecurityMetadata)
    maintenance_metadata: MaintenanceMetadata = Field(default_factory=MaintenanceMetadata)
    trust: TrustMetadata = Field(default_factory=TrustMetadata)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    dependencies: list[DependencyRequirement] = Field(default_factory=list)
    candidate_state: CandidateState = CandidateState.VERIFIED
    recommendable: bool = True
    validation_warnings: list[str] = Field(default_factory=list)
    install_complexity: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def normalize_compatibility(self) -> "Component":
        if self.compatibility and not self.supported_agents:
            self.supported_agents = set(self.compatibility.agents)
        if not self.compatibility:
            self.compatibility = Compatibility(agents=set(self.supported_agents))
        if not self.github_url and self.source_url:
            self.github_url = self.source_url
        if not self.github_url and self.repository_url:
            self.github_url = self.repository_url
        if not self.source_url and self.github_url:
            self.source_url = self.github_url
        if not self.repository_url and self.github_url:
            self.repository_url = self.github_url
        if not self.source_url:
            raise ValueError("component requires github_url or source_url")
        if self.source == "local_registry" and self.trust.source_type == SourceType.REGISTRY:
            self.trust.verified = True
            self.trust.verification_reason = "curated local registry entry"
        if self.official:
            self.trust.official = True
        return self

    def install_payload(self) -> dict[str, Any]:
        """Return non-secret installation details for Plan rendering and checks."""
        return self.install_method.model_dump(mode="json", exclude_none=True)
