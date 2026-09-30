from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import os

from pydantic import BaseModel, Field
from enum import IntEnum, StrEnum


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
    config_modified: bool = False
    completed: bool = False

    def record(self, result: ComponentInstallResult) -> None:
        self.created_paths.extend(result.created_paths)
        self.preserved_paths.extend(result.preserved_paths)
        self.configured_mcp.extend(result.configured_mcp)
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
        return cls.model_validate_json(target.read_text(encoding="utf-8"))


class InstallationResult(BaseModel):
    success: bool
    manifest: InstallationManifest
    health: HealthCheckResult | None = None
    rollback: "RollbackResult | None" = None
    error: str | None = None


class RollbackResult(BaseModel):
    restored: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors
