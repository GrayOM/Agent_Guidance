"""State must describe a component well enough to diagnose it later.

A component discovered on GitHub is never in the Local Registry, so identifying a managed
component by id alone meant it could be installed and then never appear in `doctor`,
`debug-info` or any later comparison against upstream.
"""

import json

import pytest

from grayom_agent_guidance.cli.main import _state_components
from grayom_agent_guidance.errors import ConfigurationError
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod, MultiAgentManifest,
    Ownership,
)
from grayom_agent_guidance.state import ManagedComponent, StateStore


def _managed(**overrides) -> ManagedComponent:
    values = {
        "component_id": "community-skills", "agents": [AgentType.CLAUDE_CODE],
        "ownership": Ownership.GRAYOM_INSTALLED, "transaction_id": "t",
        "component_name": "Community Skills", "component_type": ComponentType.SKILL,
        "source_repository": "https://github.com/someone/skills",
        "install_method": InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/someone/skills",
            ref="c" * 40,
        ),
    }
    values.update(overrides)
    return ManagedComponent(**values)


def test_a_github_discovered_component_can_be_rebuilt_for_diagnosis() -> None:
    restored = _managed().to_component()

    assert restored is not None
    assert restored.id == "community-skills"
    assert restored.type == ComponentType.SKILL
    assert restored.install_method.ref == "c" * 40
    assert restored.supported_agents == {AgentType.CLAUDE_CODE}


def test_a_record_written_before_these_fields_existed_is_not_guessed_at() -> None:
    """Rebuilding without an install method would invent one; the Registry fallback applies."""
    assert _managed(component_type=None, install_method=None).to_component() is None
    assert _managed(install_method=None).to_component() is None
    assert _managed(source_repository=None).to_component() is None
    assert _managed(install_method=InstallMethod()).to_component() is None


def test_doctor_sees_a_component_that_is_not_in_the_local_registry(tmp_path) -> None:
    store = StateStore(tmp_path / "state" / "components.json")
    store.document.components["community-skills"] = _managed()

    for_claude = _state_components(store, AgentType.CLAUDE_CODE)
    for_codex = _state_components(store, AgentType.CODEX)

    assert [item.id for item in for_claude] == ["community-skills"]
    assert for_codex == []


def test_a_registry_component_still_resolves_for_an_older_record(tmp_path) -> None:
    store = StateStore(tmp_path / "state" / "components.json")
    store.document.components["github"] = _managed(
        component_id="github", agents=[AgentType.CODEX],
        component_type=None, install_method=None, source_repository=None,
    )

    assert [item.id for item in _state_components(store, AgentType.CODEX)] == ["github"]


def test_recording_an_install_stores_what_diagnosis_needs(tmp_path) -> None:
    from grayom_agent_guidance.core.multi_agent_plan import build_multi_agent_plan
    from grayom_agent_guidance.models import (
        AgentInstallation, InterviewAnswer, RecommendationItem, RecommendationPlan, SetupMode,
        WorkDomain,
    )
    from grayom_agent_guidance.adapters import ClaudeCodeAdapter

    component = Component(
        id="community-skills", name="Community Skills", type=ComponentType.SKILL,
        github_url="https://github.com/someone/skills",
        capabilities={Capability.TESTING}, supported_agents={AgentType.CLAUDE_CODE},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/someone/skills",
            ref="d" * 40,
        ),
    )
    answer = InterviewAnswer(
        agents=[AgentType.CLAUDE_CODE], domains=[WorkDomain.WEB_DEVELOPMENT],
        tasks=["testing"], mode=SetupMode.MINIMAL,
    )
    recommendation = RecommendationPlan(
        interview=answer, capabilities={Capability.TESTING},
        items=[RecommendationItem(component=component, selected=True, reasons=["covers testing"])],
    )
    adapter = ClaudeCodeAdapter(home=tmp_path / "home")
    adapter.claude_home.mkdir(parents=True)
    plan = build_multi_agent_plan(
        recommendation,
        {AgentType.CLAUDE_CODE: AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True)},
        {AgentType.CLAUDE_CODE: adapter},
    )
    manifest = MultiAgentManifest(root=tmp_path / "backup", selected_agents=[AgentType.CLAUDE_CODE])
    store = StateStore(tmp_path / "state" / "components.json")
    store.record(plan, manifest)

    managed = store.document.components["community-skills"]
    assert managed.component_type == ComponentType.SKILL
    assert managed.install_method is not None
    assert managed.install_method.ref == "d" * 40
    assert managed.to_component() is not None


def test_unreadable_state_is_kept_rather_than_overwritten(tmp_path) -> None:
    """Ownership decides what update and rollback may touch, so it is never dropped silently."""
    path = tmp_path / "state" / "components.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json", encoding="utf-8")

    store = StateStore(path)

    assert store.document.components == {}
    assert any("has been kept as" in warning for warning in store.warnings)
    kept = list(path.parent.glob("components.json.damaged-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == "{ this is not json"

    store.document.components["new"] = _managed(component_id="new")
    store.save()
    assert kept[0].exists(), "the preserved document must survive the next save"


def test_state_from_a_newer_schema_is_still_refused(tmp_path) -> None:
    path = tmp_path / "state" / "components.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 99, "components": {}}), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        StateStore(path)
    assert not list(path.parent.glob("components.json.damaged-*")), (
        "a future schema is a refusal, not a damaged document"
    )
