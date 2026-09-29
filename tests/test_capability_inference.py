from grayom_agent_guidance.core import infer_capabilities
from grayom_agent_guidance.models import AgentType, Capability, InterviewAnswer, SetupMode, WorkDomain


def test_security_choices_infer_implementation_capabilities() -> None:
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )
    capabilities = infer_capabilities(answer)
    assert Capability.SECURITY_ANALYSIS in capabilities
    assert Capability.SOURCE_ANALYSIS in capabilities
    assert Capability.REPORT_SUPPORT in capabilities

