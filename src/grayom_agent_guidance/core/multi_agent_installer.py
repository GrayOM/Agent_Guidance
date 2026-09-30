import hashlib
from datetime import datetime, timezone
from pathlib import Path

from grayom_agent_guidance.adapters import AgentAdapter
from grayom_agent_guidance.models import (
    AgentType, ComponentType, InstallationManifest, MultiAgentInstallationResult,
    MultiAgentManifest, MultiAgentPlan, TransactionState,
)

from .shared_components import SharedComponentManager
from grayom_agent_guidance.runtime import validate_managed_path


def _hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MultiAgentInstallationTransaction:
    def __init__(self, adapters: dict[AgentType, AgentAdapter], backup_root: Path) -> None:
        self.adapters = adapters
        self.backup_root = backup_root
        self.shared = SharedComponentManager()

    def _destination(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = self.backup_root / stamp
        validate_managed_path(destination, self.backup_root)
        return destination

    def execute(self, plan: MultiAgentPlan, probe_mcp: bool = True) -> MultiAgentInstallationResult:
        root = self._destination()
        manifest = MultiAgentManifest(
            root=root, selected_agents=list(plan.agents), shared_components=plan.shared_components,
        )
        manifest.save()
        try:
            # Back up every selected Agent before the first mutation.
            manifest.state = TransactionState.BACKING_UP
            manifest.save()
            for agent, agent_plan in plan.agents.items():
                adapter = self.adapters[agent]
                for path in adapter.get_config_paths():
                    manifest.original_hashes[f"{agent.value}:{path}"] = _hash(path)
                backup = adapter.backup(root / agent.value)
                agent_manifest = InstallationManifest(backup=backup)
                agent_manifest.save()
                manifest.agent_manifests[agent] = agent_manifest
            manifest.save()

            manifest.state = TransactionState.APPLYING
            manifest.save()
            component_by_id = {
                action.component.id: action.component
                for agent_plan in plan.agents.values() for action in agent_plan.actions
            }
            for record in manifest.shared_components:
                self.shared.prepare(component_by_id[record.component_id], record)
            manifest.save()

            for agent, agent_plan in plan.agents.items():
                adapter = self.adapters[agent]
                agent_manifest = manifest.agent_manifests[agent]
                for component in agent_plan.components:
                    if component.type == ComponentType.SKILL:
                        change = adapter.install_skill(component)
                    elif component.type == ComponentType.MCP:
                        change = adapter.configure_mcp(component)
                        agent_manifest.config_modified |= change.changed
                    else:
                        change = adapter.install_plugin(component)
                    agent_manifest.record(change)
                    agent_manifest.save()

            manifest.state = TransactionState.VERIFYING
            manifest.save()
            health = {}
            fatal = []
            for agent, agent_plan in plan.agents.items():
                result = self.adapters[agent].health_check(
                    agent_plan.expected_components, probe_mcp=probe_mcp,
                )
                health[agent] = result
                fatal.extend(
                    f"{agent.value}:{check.name}" for check in result.checks
                    if not check.passed and check.fatal
                )
            if fatal:
                raise RuntimeError("fatal Health Check failure: " + ", ".join(fatal))
            for agent in plan.agents:
                for path in self.adapters[agent].get_config_paths():
                    manifest.post_install_hashes[f"{agent.value}:{path}"] = _hash(path)
            for agent_manifest in manifest.agent_manifests.values():
                agent_manifest.completed = True
                agent_manifest.save()
            manifest.completed = True
            manifest.state = TransactionState.COMMITTED
            manifest.save()
            return MultiAgentInstallationResult(success=True, manifest=manifest, health=health)
        except (Exception, KeyboardInterrupt) as exc:
            manifest.error = str(exc)
            manifest.state = TransactionState.ROLLING_BACK
            manifest.save()
            rollbacks = {}
            for agent in reversed(list(manifest.agent_manifests)):
                result = self.adapters[agent].rollback(manifest.agent_manifests[agent])
                rollbacks[agent] = result
                manifest.rollback_errors.extend(
                    f"{agent.value}: {error}" for error in result.errors
                )
            manifest.state = (
                TransactionState.FAILED if manifest.rollback_errors else TransactionState.ROLLED_BACK
            )
            manifest.save()
            return MultiAgentInstallationResult(
                success=False, manifest=manifest, rollbacks=rollbacks, error=str(exc),
            )


def rollback_multi_agent(
    manifest: MultiAgentManifest, adapters: dict[AgentType, AgentAdapter],
) -> dict[AgentType, object]:
    manifest.state = TransactionState.ROLLING_BACK
    manifest.save()
    results = {}
    for agent in reversed(list(manifest.agent_manifests)):
        if agent not in adapters:
            continue
        results[agent] = adapters[agent].rollback(manifest.agent_manifests[agent])
    errors = [error for result in results.values() for error in result.errors]
    manifest.rollback_errors.extend(errors)
    manifest.state = TransactionState.FAILED if errors else TransactionState.ROLLED_BACK
    manifest.save()
    return results


def find_incomplete_transactions(root: Path) -> list[MultiAgentManifest]:
    incomplete: list[MultiAgentManifest] = []
    terminal = {TransactionState.COMMITTED, TransactionState.ROLLED_BACK, TransactionState.FAILED}
    if not root.exists():
        return incomplete
    for path in sorted(root.glob("*/manifest.json")):
        try:
            manifest = MultiAgentManifest.load(path)
        except (OSError, ValueError):
            continue
        if manifest.state not in terminal:
            incomplete.append(manifest)
    return incomplete
