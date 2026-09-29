from abc import ABC, abstractmethod
from pathlib import Path

from grayom_agent_guidance.models import (
    AgentInstallation, BackupManifest, Component, HealthCheckResult, RollbackResult,
)


class AgentAdapter(ABC):
    @abstractmethod
    def detect(self) -> AgentInstallation: ...

    @abstractmethod
    def inspect(self) -> dict[str, object]: ...

    @abstractmethod
    def backup(self, destination: Path) -> BackupManifest: ...

    @abstractmethod
    def install_skill(self, component: Component) -> None: ...

    @abstractmethod
    def configure_mcp(self, component: Component) -> None: ...

    @abstractmethod
    def install_plugin(self, component: Component) -> None: ...

    @abstractmethod
    def health_check(self) -> HealthCheckResult: ...

    @abstractmethod
    def rollback(self, manifest: BackupManifest) -> RollbackResult: ...

