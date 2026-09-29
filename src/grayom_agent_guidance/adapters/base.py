from abc import ABC, abstractmethod
from pathlib import Path

from grayom_agent_guidance.models import (
    AgentInstallation, BackupManifest, Component, ComponentInstallResult,
    HealthCheckResult, InstallationManifest, RollbackResult,
)


class AgentAdapter(ABC):
    @abstractmethod
    def detect(self) -> AgentInstallation: ...

    @abstractmethod
    def inspect(self) -> dict[str, object]: ...

    @abstractmethod
    def backup(self, destination: Path) -> BackupManifest: ...

    @abstractmethod
    def install_skill(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def configure_mcp(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def install_plugin(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def health_check(
        self, expected: list[Component] | None = None, probe_mcp: bool = True,
    ) -> HealthCheckResult: ...

    @abstractmethod
    def rollback(self, manifest: InstallationManifest) -> RollbackResult: ...
