from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import os

from pydantic import BaseModel, Field
from enum import IntEnum, StrEnum

from agent_guidance.schema import load_versioned_json


class HealthLevel(IntEnum):
    STATIC = 1
    INITIALIZATION = 2
    FUNCTIONAL = 3


class HealthStatus(StrEnum):
    PASS = "PASS"  # nosec B105
    WARNING = "WARNING"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class BackupEntry(BaseModel):
    original: Path
    backup: Path | None = None
    existed: bool


class BackupManifest(BaseModel):
    schema_version: int = 1
    root: Path
    entries: list[BackupEntry] = Field(default_factory=list)


class CheckResult(BaseModel):
    name: str
    passed: bool
    message: str
    fatal: bool = True
    level: HealthLevel = HealthLevel.STATIC
    status: HealthStatus | None = None

    def model_post_init(self, __context: object) -> None:
        if self.status is None:
            self.status = HealthStatus.PASS if self.passed else (
                HealthStatus.FAIL if self.fatal else HealthStatus.WARNING
            )


class HealthCheckResult(BaseModel):
    checks: list[CheckResult]

    @property
    def healthy(self) -> bool:
        return all(check.passed or not check.fatal for check in self.checks)


class ComponentInstallResult(BaseModel):
    component_id: str
    changed: bool = False
    created_paths: list[Path] = Field(default_factory=list)
    preserved_paths: list[Path] = Field(default_factory=list)
    configured_mcp: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # What a Skill repository offered and what was taken from it, so the user can be told
    # in one line what landed instead of discovering it in their Agent's context.
    skills_available: int = 0
    skills_selected: list[str] = Field(default_factory=list)
    skills_skipped: dict[str, int] = Field(default_factory=dict)
    # Plugins and marketplaces are undone by an inverse command rather than a file, so what
    # was added has to be recorded for rollback to be able to reverse exactly that much.
    installed_plugins: list[str] = Field(default_factory=list)
    added_marketplaces: list[str] = Field(default_factory=list)


class InstallationManifest(BaseModel):
    schema_version: int = 1
    transaction_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    backup: BackupManifest
    created_paths: list[Path] = Field(default_factory=list)
    preserved_paths: list[Path] = Field(default_factory=list)
    installed_components: list[str] = Field(default_factory=list)
    preexisting_components: list[str] = Field(default_factory=list)
    configured_mcp: list[str] = Field(default_factory=list)
    installed_plugins: list[str] = Field(default_factory=list)
    added_marketplaces: list[str] = Field(default_factory=list)
    config_modified: bool = False
    completed: bool = False

    def record(self, result: ComponentInstallResult) -> None:
        self.created_paths.extend(result.created_paths)
        self.preserved_paths.extend(result.preserved_paths)
        self.configured_mcp.extend(result.configured_mcp)
        self.installed_plugins.extend(result.installed_plugins)
        self.added_marketplaces.extend(result.added_marketplaces)
        target = self.installed_components if result.changed else self.preexisting_components
        if result.component_id not in target:
            target.append(result.component_id)

    @property
    def path(self) -> Path:
        return self.backup.root / "manifest.json"

    def save(self) -> None:
        self.backup.root.mkdir(parents=True, exist_ok=True)
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
    def load(cls, path: Path) -> "InstallationManifest":
        target = path / "manifest.json" if path.is_dir() else path
        # Refuse a manifest written by a newer Agent Guidance instead of restoring it with fields dropped.
        return cls.model_validate(load_versioned_json(target))


class InstallationResult(BaseModel):
    success: bool
    manifest: InstallationManifest
    health: HealthCheckResult | None = None
    rollback: "RollbackResult | None" = None
    error: str | None = None


class ComponentRemovalResult(BaseModel):
    """What an uninstall took away from one Agent, and what it deliberately left.

    `preserved` is as important as `removed`: a component the user already had, a file they
    changed after install, or a registration Agent Guidance never wrote is not Agent Guidance's to delete,
    and the run has to say so rather than silently doing less than it reported.
    """

    component_id: str
    # Recorded paths that belong to this Agent. State keeps one path list per component
    # across every Agent, so a count of what was removed means nothing without it.
    owned_paths: int = 0
    removed_paths: list[Path] = Field(default_factory=list)
    removed_mcp: list[str] = Field(default_factory=list)
    removed_plugins: list[str] = Field(default_factory=list)
    removed_marketplaces: list[str] = Field(default_factory=list)
    preserved: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    changed: bool = False

    @property
    def successful(self) -> bool:
        return not self.errors


class RollbackResult(BaseModel):
    restored: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors
