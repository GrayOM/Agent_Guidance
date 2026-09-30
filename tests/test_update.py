from grayom_agent_guidance.core.update import build_update_plan
from grayom_agent_guidance.models import AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod, Ownership
from grayom_agent_guidance.state import ManagedComponent, StateStore


def test_update_only_targets_grayom_managed_components(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.document.components = {
        "managed": ManagedComponent(
            component_id="managed", agents=[AgentType.CODEX], ownership=Ownership.GRAYOM_INSTALLED,
            source_ref="old", transaction_id="one",
        ),
        "existing": ManagedComponent(
            component_id="existing", agents=[AgentType.CODEX], ownership=Ownership.EXISTING,
            source_ref="old", transaction_id="one",
        ),
    }
    candidates = [Component(
        id=name, name=name, type=ComponentType.SKILL,
        github_url=f"https://github.com/example/{name}", supported_agents={AgentType.CODEX},
        capabilities={Capability.TESTING},
        install_method=InstallMethod(kind=InstallKind.GIT_SKILLS, repository=f"https://github.com/example/{name}", ref="new"),
    ) for name in ("managed", "existing")]
    plan = build_update_plan(state, candidates)
    assert [item.component.id for item in plan.items] == ["managed"]
