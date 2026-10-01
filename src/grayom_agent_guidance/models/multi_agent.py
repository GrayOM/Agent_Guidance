from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
import os

from pydantic import BaseModel, Field

from .agent import AgentType
from .component import Component, ComponentType
from .installation import HealthCheckResult, InstallationManifest, RollbackResult
from .reconciliation import ReconciliationStatus
from grayom_agent_guidance.schema import load_versioned_json


class CompatibilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class Ownership(StrEnum):
    EXISTING = "EXISTING"
    GRAYOM_INSTALLED = "GRAYOM_INSTALLED"
    GRAYOM_MODIFIED = "GRAYOM_MODIFIED"
    SHARED = "SHARED"


class TransactionState(StrEnum):
    PREPARED = "PREPARED"
    BACKING_UP = "BACKING_UP"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"
    COMMITTED = "COMMITTED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class CompatibilityResult(BaseModel):
    agent: AgentType
    component_id: str
    status: CompatibilityStatus
    reason: str
    evidence: list[str] = Field(default_factory=list)


class AgentComponentAction(BaseModel):
    component: Component
    compatibility: CompatibilityResult
    install: bool
    already_installed: bool = False
    reason: str
    reconciliation: ReconciliationStatus = ReconciliationStatus.ADD


class AgentPlan(BaseModel):
    agent: AgentType
    version: str | None = None
    actions: list[AgentComponentAction] = Field(default_factory=list)

    @property
    def components(self) -> list[Component]:
        return [action.component for action in self.actions if action.install]

    @property
    def expected_components(self) -> list[Component]:
        return [
            action.component for action in self.actions
            if action.install or action.already_installed
        ]


class SharedComponentRecord(BaseModel):
    component_id: str
    ownership: Ownership
    shared: bool
    used_by: list[AgentType]
    installation_path: Path | None = None
    prepared_count: int = 1


class MultiAgentPlan(BaseModel):
    agents: dict[AgentType, AgentPlan]
    shared_components: list[SharedComponentRecord] = Field(default_factory=list)


class InstalledComponent(BaseModel):
    """What actually landed for one Agent, so it can be summarised in a single line."""

    agent: AgentType
    component_id: str
    name: str
    type: ComponentType
    changed: bool = False
    skills_available: int = 0
    skills_selected: list[str] = Field(default_factory=list)
    skills_skipped: dict[str, int] = Field(default_factory=dict)
    configured_mcp: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        if self.type == ComponentType.SKILL:
            if not self.skills_selected:
                return f"no Skill matched (of {self.skills_available} in the repository)"
            shown = ", ".join(self.skills_selected[:3])
            if len(self.skills_selected) > 3:
                shown += f", +{len(self.skills_selected) - 3} more"
            scope = (
                f"{len(self.skills_selected)} of {self.skills_available} Skills"
                if self.skills_available > len(self.skills_selected)
                else f"{len(self.skills_selected)} Skills"
            )
            return f"{scope}: {shown}"
        if self.type == ComponentType.MCP:
            registered = ", ".join(self.configured_mcp) or self.component_id
            return f"MCP registered as {registered}" if self.changed else "MCP already registered"
        return "installed"


class MultiAgentManifest(BaseModel):
    schema_version: int = 1
    transaction_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    root: Path
    selected_agents: list[AgentType]
    agent_manifests: dict[AgentType, InstallationManifest] = Field(default_factory=dict)
    shared_components: list[SharedComponentRecord] = Field(default_factory=list)
    completed: bool = False
    state: TransactionState = TransactionState.PREPARED
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    rollback_errors: list[str] = Field(default_factory=list)
    original_hashes: dict[str, str | None] = Field(default_factory=dict)
    post_install_hashes: dict[str, str | None] = Field(default_factory=dict)
    shared_warnings: list[str] = Field(default_factory=list)
    outcomes: list[InstalledComponent] = Field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.root / "manifest.json"

    def save(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(self.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: Path) -> "MultiAgentManifest":
        target = path / "manifest.json" if path.is_dir() else path
        # Refuse a manifest written by a newer GrayOM instead of restoring it with fields dropped.
        return cls.model_validate(load_versioned_json(target))


class MultiAgentInstallationResult(BaseModel):
    success: bool
    manifest: MultiAgentManifest
    health: dict[AgentType, HealthCheckResult] = Field(default_factory=dict)
    rollbacks: dict[AgentType, RollbackResult] = Field(default_factory=dict)
    error: str | None = None
