import shutil
import tomllib
from pathlib import Path

from grayom_agent_guidance.models import (
    AgentInstallation, AgentType, BackupEntry, BackupManifest, CheckResult, Component,
    HealthCheckResult, RollbackResult,
)

from .base import AgentAdapter


class CodexAdapter(AgentAdapter):
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()
        self.codex_home = self.home / ".codex"
        self.config_path = self.codex_home / "config.toml"

    def detect(self) -> AgentInstallation:
        executable = shutil.which("codex")
        detected = bool(executable or self.codex_home.exists())
        return AgentInstallation(
            agent=AgentType.CODEX, detected=detected,
            executable=Path(executable) if executable else None,
            config_path=self.config_path if self.config_path.exists() else None,
        )

    def inspect(self) -> dict[str, object]:
        return {
            "codex_home": self.codex_home,
            "config_exists": self.config_path.exists(),
            "skills_directories": [
                path for path in (self.codex_home / "skills", self.codex_home / ".skills")
                if path.exists()
            ],
        }

    def backup(self, destination: Path) -> BackupManifest:
        destination.mkdir(parents=True, exist_ok=True)
        entries: list[BackupEntry] = []
        if self.config_path.exists():
            target = destination / "config.toml"
            shutil.copy2(self.config_path, target)
            entries.append(BackupEntry(original=self.config_path, backup=target))
        return BackupManifest(root=destination, entries=entries)

    def install_skill(self, component: Component) -> None:
        raise NotImplementedError("skill installation is scheduled for the next MVP increment")

    def configure_mcp(self, component: Component) -> None:
        raise NotImplementedError("MCP configuration is scheduled for the next MVP increment")

    def install_plugin(self, component: Component) -> None:
        raise NotImplementedError("plugin installation is scheduled for the next MVP increment")

    def health_check(self) -> HealthCheckResult:
        checks = [CheckResult(
            name="codex_detected", passed=self.detect().detected,
            message="Codex executable or home directory detected" if self.detect().detected
            else "Codex was not detected",
        )]
        if self.config_path.exists():
            try:
                with self.config_path.open("rb") as stream:
                    tomllib.load(stream)
                checks.append(CheckResult(name="config_parse", passed=True, message="config.toml is valid"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                checks.append(CheckResult(name="config_parse", passed=False, message=str(exc)))
        else:
            checks.append(CheckResult(name="config_parse", passed=True, message="no config.toml to parse"))
        return HealthCheckResult(checks=checks)

    def rollback(self, manifest: BackupManifest) -> RollbackResult:
        result = RollbackResult()
        for entry in manifest.entries:
            try:
                entry.original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry.backup, entry.original)
                result.restored.append(entry.original)
            except OSError as exc:
                result.errors.append(f"{entry.original}: {exc}")
        return result

