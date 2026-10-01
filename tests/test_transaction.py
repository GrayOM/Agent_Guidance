import shutil
from pathlib import Path

from grayom_agent_guidance.adapters import AgentAdapter
from grayom_agent_guidance.core import MultiAgentInstallationTransaction, find_incomplete_transactions
from grayom_agent_guidance.models import (
    AdapterCapabilities, AgentComponentAction, AgentInstallation, AgentPlan, AgentType, BackupEntry, BackupManifest,
    CheckResult, CompatibilityResult, CompatibilityStatus, Component, ComponentInstallResult,
    ComponentType, HealthCheckResult, InstallationManifest, MultiAgentPlan, RollbackResult,
    TransactionState,
)


class FakeAdapter(AgentAdapter):
    @property
    def capabilities(self): return AdapterCapabilities(skills=True, mcp=True, plugins=True, health_probe=True)

    def __init__(self, agent: AgentType, root: Path, fail: bool = False) -> None:
        self.agent, self.root, self.fail = agent, root, fail
        self.config = root / "config.json"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("original", encoding="utf-8")

    def detect(self): return AgentInstallation(agent=self.agent, detected=True)
    def inspect(self): return {"skills": [], "mcp_servers": [], "plugins": []}
    def get_version(self): return "1.0.0"
    def get_config_paths(self): return [self.config]
    def list_existing_skills(self): return []
    def list_existing_mcps(self): return []
    def list_existing_plugins(self): return []
    def backup(self, destination):
        destination.mkdir(parents=True)
        target = destination / "config.json"
        shutil.copy2(self.config, target)
        return BackupManifest(root=destination, entries=[BackupEntry(original=self.config, backup=target, existed=True)])
    def install_skill(self, component):
        self.config.write_text("changed", encoding="utf-8")
        return ComponentInstallResult(component_id=component.id, changed=True)
    def configure_mcp(self, component): return self.install_skill(component)
    def install_plugin(self, component): return self.install_skill(component)
    def health_check(self, expected=None, probe_mcp=True):
        return HealthCheckResult(checks=[CheckResult(name="health", passed=not self.fail, message="test")])
    def rollback(self, manifest: InstallationManifest):
        result = RollbackResult()
        for entry in manifest.backup.entries:
            shutil.copy2(entry.backup, entry.original)
            result.restored.append(entry.original)
        return result


def _plan() -> MultiAgentPlan:
    component = Component(
        id="skill", name="Skill", type=ComponentType.SKILL,
        github_url="https://github.com/example/skill", supported_agents=set(AgentType),
    )
    agents = {}
    for agent in AgentType:
        compatibility = CompatibilityResult(
            agent=agent, component_id="skill", status=CompatibilityStatus.SUPPORTED,
            reason="supported",
        )
        agents[agent] = AgentPlan(agent=agent, actions=[AgentComponentAction(
            component=component, compatibility=compatibility, install=True, reason="add",
        )])
    return MultiAgentPlan(agents=agents)


def test_a_later_agent_failure_rolls_back_every_agent(tmp_path) -> None:
    adapters = {
        agent: FakeAdapter(agent, tmp_path / agent.value, fail=agent == AgentType.CLAUDE_CODE)
        for agent in AgentType
    }
    result = MultiAgentInstallationTransaction(adapters, tmp_path / "backups").execute(_plan())
    assert not result.success
    assert result.manifest.state == TransactionState.ROLLED_BACK
    assert all(adapter.config.read_text(encoding="utf-8") == "original" for adapter in adapters.values())
    assert set(result.rollbacks) == set(AgentType)


def test_successful_transaction_is_committed_and_not_incomplete(tmp_path) -> None:
    adapters = {agent: FakeAdapter(agent, tmp_path / agent.value) for agent in AgentType}
    root = tmp_path / "backups"
    result = MultiAgentInstallationTransaction(adapters, root).execute(_plan())
    assert result.success
    assert result.manifest.state == TransactionState.COMMITTED
    assert result.manifest.completed
    assert find_incomplete_transactions(root) == []


def test_prepared_manifest_is_detected_for_crash_recovery(tmp_path) -> None:
    from grayom_agent_guidance.models import MultiAgentManifest

    manifest = MultiAgentManifest(root=tmp_path / "backups" / "crashed", selected_agents=[AgentType.CODEX])
    manifest.save()
    found = find_incomplete_transactions(tmp_path / "backups")
    assert [item.transaction_id for item in found] == [manifest.transaction_id]
