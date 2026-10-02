from agent_guidance.core import infer_capabilities
from agent_guidance.models import AgentType, Capability, InterviewAnswer, SetupMode, WorkDomain


def test_security_choices_infer_implementation_capabilities() -> None:
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )
    capabilities = infer_capabilities(answer)
    assert Capability.SECURITY_ANALYSIS in capabilities
    assert Capability.SOURCE_ANALYSIS in capabilities
    assert Capability.REPORTING in capabilities
    assert Capability.CODE_EDITING in capabilities
    assert Capability.TESTING in capabilities
    assert Capability.REPOSITORY_ACCESS in capabilities
