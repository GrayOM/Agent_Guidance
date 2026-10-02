from agent_guidance.core import evaluate_compatibility
from agent_guidance.models import (
    AgentInstallation, AgentRequirement, AgentType, Capability, CompatibilityStatus,
    Component, ComponentType,
)


def test_unknown_version_is_not_treated_as_supported() -> None:
    component = Component(
        id="future", name="Future", type=ComponentType.SKILL,
        github_url="https://github.com/example/future", supported_agents={AgentType.CLAUDE_CODE},
        capabilities={Capability.TESTING},
        agent_requirements={AgentType.CLAUDE_CODE: AgentRequirement(min_version="2.1.0")},
    )
    result = evaluate_compatibility(
        component, AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True),
    )
    assert result.status == CompatibilityStatus.UNKNOWN


def test_component_can_be_supported_for_one_agent_and_unsupported_for_another() -> None:
    component = Component(
        id="one", name="One", type=ComponentType.SKILL,
        github_url="https://github.com/example/one", supported_agents={AgentType.CODEX},
        capabilities={Capability.TESTING},
    )
    codex = evaluate_compatibility(component, AgentInstallation(agent=AgentType.CODEX, detected=True))
    claude = evaluate_compatibility(component, AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True))
    assert codex.status == CompatibilityStatus.SUPPORTED
    assert claude.status == CompatibilityStatus.UNSUPPORTED
