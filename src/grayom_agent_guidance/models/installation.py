from pathlib import Path

from pydantic import BaseModel, Field


class BackupEntry(BaseModel):
    original: Path
    backup: Path


class BackupManifest(BaseModel):
    root: Path
    entries: list[BackupEntry] = Field(default_factory=list)


class CheckResult(BaseModel):
    name: str
    passed: bool
    message: str


class HealthCheckResult(BaseModel):
    checks: list[CheckResult]

    @property
    def healthy(self) -> bool:
        return all(check.passed for check in self.checks)


class RollbackResult(BaseModel):
    restored: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors

