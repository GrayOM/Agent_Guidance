from grayom_agent_guidance.core import recommend
from grayom_agent_guidance.models import AgentType, InterviewAnswer, SetupMode, WorkDomain
from grayom_agent_guidance.registry import load_registry


def test_minimal_does_not_select_redundant_components() -> None:
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )
    plan = recommend(answer, load_registry())
    assert plan.selected
    selected_ids = {item.id for item in plan.selected}
    assert "trailofbits-skills" in selected_ids

