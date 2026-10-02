from agent_guidance.core import recommend
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InterviewAnswer, SetupMode, WorkDomain,
)
from agent_guidance.registry import load_registry


def test_minimal_does_not_select_redundant_components() -> None:
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )
    plan = recommend(answer, load_registry())
    assert plan.selected
    selected_ids = {item.id for item in plan.selected}
    assert "trailofbits-skills" in selected_ids
    assert not ({"superpowers", "addy-agent-skills"} <= selected_ids)
    skipped = {item.component.id: item.reasons for item in plan.items if not item.selected}
    assert any("overlaps" in reason for reason in skipped["addy-agent-skills"])


def test_performance_selects_more_coverage_than_minimal() -> None:
    base = dict(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"],
    )
    minimal = recommend(InterviewAnswer(**base, mode=SetupMode.MINIMAL), load_registry())
    performance = recommend(InterviewAnswer(**base, mode=SetupMode.PERFORMANCE), load_registry())
    assert len(performance.selected) >= len(minimal.selected)


def test_duplicate_mcp_is_removed_even_in_performance_mode() -> None:
    def candidate(identifier: str, score: int) -> Component:
        return Component(
            id=identifier, name=identifier, type=ComponentType.MCP,
            github_url=f"https://github.com/example/{identifier}",
            supported_agents={AgentType.CODEX}, capabilities={Capability.REPOSITORY_ACCESS},
            quality_score=score,
        )

    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.GENERAL_DEVELOPMENT],
        mode=SetupMode.PERFORMANCE,
    )
    plan = recommend(answer, [candidate("official", 90), candidate("duplicate", 70)])
    assert [item.id for item in plan.selected] == ["official"]
    duplicate = next(item for item in plan.items if item.component.id == "duplicate")
    assert "duplicates MCP" in duplicate.reasons[0]
