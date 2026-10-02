from datetime import datetime, timezone
from pathlib import Path

from agent_guidance.adapters import AgentAdapter
from agent_guidance.models import (
    Component, ComponentType, InstallationManifest, InstallationResult,
)


class InstallationTransaction:
    def __init__(self, adapter: AgentAdapter, backup_root: Path) -> None:
        self.adapter = adapter
        self.backup_root = backup_root

    def _destination(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return self.backup_root / stamp

    def execute(self, components: list[Component], probe_mcp: bool = True) -> InstallationResult:
        backup = self.adapter.backup(self._destination())
        manifest = InstallationManifest(backup=backup)
        manifest.save()
        try:
            for component in components:
                if component.type == ComponentType.SKILL:
                    change = self.adapter.install_skill(component)
                elif component.type == ComponentType.MCP:
                    change = self.adapter.configure_mcp(component)
                    manifest.config_modified = manifest.config_modified or change.changed
                elif component.type == ComponentType.PLUGIN:
                    change = self.adapter.install_plugin(component)
                else:  # pragma: no cover - enum prevents this
                    raise RuntimeError(f"unsupported component type: {component.type}")
                manifest.record(change)
                manifest.save()
            health = self.adapter.health_check(components, probe_mcp=probe_mcp)
            if not health.healthy:
                failed = ", ".join(check.name for check in health.checks if not check.passed and check.fatal)
                raise RuntimeError(f"fatal Health Check failure: {failed}")
            manifest.completed = True
            manifest.save()
            return InstallationResult(success=True, manifest=manifest, health=health)
        except Exception as exc:
            rollback = self.adapter.rollback(manifest)
            manifest.save()
            return InstallationResult(
                success=False, manifest=manifest, rollback=rollback, error=str(exc),
            )
