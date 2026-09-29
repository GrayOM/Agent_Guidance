from grayom_agent_guidance.core import explain_plan
from grayom_agent_guidance.models import AgentType, InterviewAnswer, RecommendationPlan, SetupMode, WorkDomain
from grayom_agent_guidance.core import recommend
from grayom_agent_guidance.registry import load_registry


def test_explainer_links_components_to_user_work() -> None:
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )
    explanation = explain_plan(recommend(answer, load_registry()))
    assert explanation.components
    assert any("Security Tool Development" in reason for item in explanation.components for reason in item.reasons)
