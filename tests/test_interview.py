from grayom_agent_guidance.cli.interview import build_answer
from grayom_agent_guidance.models import AgentType, SetupMode, WorkDomain


def test_interview_accepts_multiple_domains_and_tasks() -> None:
    answer = build_answer(
        [AgentType.CODEX],
        [WorkDomain.SECURITY_TOOL_DEVELOPMENT, WorkDomain.VULNERABILITY_RESEARCH],
        ["source_code_analysis", "oss_vulnerability_research", "security_report_automation"],
        SetupMode.MINIMAL,
    )
    assert len(answer.domains) == 2
    assert len(answer.tasks) == 3
