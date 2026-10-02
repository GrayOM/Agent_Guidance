from agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
from agent_guidance.core import build_multi_agent_plan
from agent_guidance.models import (
    AgentInstallation, AgentType, Capability, Component, ComponentType, InterviewAnswer,
    RecommendationItem, RecommendationPlan, SetupMode, WorkDomain,
)


def test_unsupported_agent_does_not_discard_supported_agent_install(tmp_path) -> None:
    component = Component(
        id="codex-only", name="Codex only", type=ComponentType.SKILL,
        github_url="https://github.com/example/one", supported_agents={AgentType.CODEX},
        capabilities={Capability.TESTING},
    )
    answer = InterviewAnswer(
        agents=[AgentType.CODEX, AgentType.CLAUDE_CODE], domains=[WorkDomain.GENERAL_DEVELOPMENT],
        mode=SetupMode.MINIMAL,
    )
    recommendation = RecommendationPlan(
        interview=answer, capabilities={Capability.TESTING},
        items=[RecommendationItem(component=component, selected=True, reasons=["testing"])],
    )
    installations = {
        AgentType.CODEX: AgentInstallation(agent=AgentType.CODEX, detected=True),
        AgentType.CLAUDE_CODE: AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True),
    }
    adapters = {
        AgentType.CODEX: CodexAdapter(tmp_path / "codex"),
        AgentType.CLAUDE_CODE: ClaudeCodeAdapter(tmp_path / "claude"),
    }
    multi = build_multi_agent_plan(recommendation, installations, adapters)
    assert multi.agents[AgentType.CODEX].actions[0].install
    assert not multi.agents[AgentType.CLAUDE_CODE].actions[0].install
    assert multi.agents[AgentType.CLAUDE_CODE].actions[0].compatibility.status.value == "UNSUPPORTED"
