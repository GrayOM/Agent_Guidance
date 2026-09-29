import shutil
from pathlib import Path

from grayom_agent_guidance.adapters import AgentAdapter
from grayom_agent_guidance.core import MultiAgentInstallationTransaction
from grayom_agent_guidance.models import (
    AgentComponentAction, AgentInstallation, AgentPlan, AgentType, BackupEntry, BackupManifest,
    CheckResult, CompatibilityResult, CompatibilityStatus, Component, ComponentInstallResult,
    ComponentType, HealthCheckResult, InstallationManifest, MultiAgentPlan, RollbackResult,
)


class FakeAdapter(AgentAdapter):
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


def test_third_agent_failure_rolls_back_every_agent(tmp_path) -> None:
    adapters = {
        agent: FakeAdapter(agent, tmp_path / agent.value, fail=agent == AgentType.CURSOR)
        for agent in AgentType
    }
    result = MultiAgentInstallationTransaction(adapters, tmp_path / "backups").execute(_plan())
    assert not result.success
    assert all(adapter.config.read_text(encoding="utf-8") == "original" for adapter in adapters.values())
    assert set(result.rollbacks) == set(AgentType)
