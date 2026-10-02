from abc import ABC, abstractmethod
from pathlib import Path

from agent_guidance.models import (
    AdapterCapabilities, AgentInstallation, BackupManifest, Component, ComponentInstallResult,
    ComponentRemovalResult, HealthCheckResult, InstallationManifest, RollbackResult,
)


class AgentAdapter(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def detect(self) -> AgentInstallation: ...

    @abstractmethod
    def inspect(self) -> dict[str, object]: ...

    @abstractmethod
    def get_version(self) -> str | None: ...

    @abstractmethod
    def get_config_paths(self) -> list[Path]: ...

    @abstractmethod
    def list_existing_skills(self) -> list[str]: ...

    @abstractmethod
    def list_existing_mcps(self) -> list[str]: ...

    @abstractmethod
    def list_existing_plugins(self) -> list[str]: ...

    @abstractmethod
    def backup(self, destination: Path) -> BackupManifest: ...

    @abstractmethod
    def install_skill(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def configure_mcp(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def install_plugin(self, component: Component) -> ComponentInstallResult: ...

    @abstractmethod
    def remove_component(
        self,
        component: Component,
        paths: list[Path],
        file_hashes: dict[str, str],
        mcp_names: list[str],
        marketplaces: list[str],
    ) -> ComponentRemovalResult:
        """Take away exactly what Agent Guidance put in for this Agent, and nothing else.

        Every argument is what state recorded at install time rather than what the adapter
        can infer now: an MCP may have landed under an alias, and a Skill directory the user
        has edited since is no longer Agent Guidance's to delete.
        """

    @abstractmethod
    def health_check(
        self, expected: list[Component] | None = None, probe_mcp: bool = True,
    ) -> HealthCheckResult: ...

    @abstractmethod
    def rollback(self, manifest: InstallationManifest) -> RollbackResult: ...
