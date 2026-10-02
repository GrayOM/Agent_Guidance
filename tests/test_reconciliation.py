from agent_guidance.adapters import CodexAdapter
from agent_guidance.core.reconcile import reconcile_component
from agent_guidance.models import (
    AgentType, Capability, CompatibilityStatus, Component, ComponentType,
    ReconciliationStatus,
)


def test_missing_component_is_add_and_existing_component_is_unchanged(tmp_path) -> None:
    adapter = CodexAdapter(tmp_path / "home")
    component = Component(
        id="demo", name="Demo", type=ComponentType.SKILL,
        github_url="https://github.com/example/demo", supported_agents={AgentType.CODEX},
        capabilities={Capability.TESTING},
    )
    first = reconcile_component(AgentType.CODEX, component, CompatibilityStatus.SUPPORTED, adapter)
    target = adapter.skills_root / "demo--one"
    target.mkdir(parents=True)
    target.joinpath("SKILL.md").write_text("---\nname: one\ndescription: one\n---\n", encoding="utf-8")
    second = reconcile_component(AgentType.CODEX, component, CompatibilityStatus.SUPPORTED, adapter)
    assert first.status == ReconciliationStatus.ADD
    assert second.status == ReconciliationStatus.UNCHANGED
