import sys

from InquirerPy import inquirer

from grayom_agent_guidance.models import AgentInstallation, AgentType, InterviewAnswer, SetupMode, WorkDomain


DOMAIN_LABELS = {domain.value.replace("_", " ").title(): domain for domain in WorkDomain}
TASKS = {
    WorkDomain.WEB_DEVELOPMENT: ["frontend", "backend", "full_stack", "api_development", "testing", "code_review", "performance_optimization", "security_review"],
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: ["source_code_analysis", "security_report_automation"],
    WorkDomain.VULNERABILITY_RESEARCH: ["oss_vulnerability_research", "cve_analysis", "patch_analysis", "supply_chain_security", "ai_llm_security"],
    WorkDomain.OSINT: ["osint_recon"],
    WorkDomain.AI_AGENT_DEVELOPMENT: ["coding_agent", "research_agent", "security_agent", "browser_agent", "data_agent", "multi_agent", "mcp_based_agent", "rag_agent"],
}

TASKS[WorkDomain.VULNERABILITY_RESEARCH].append("ai_vulnerability_analysis")


def build_answer(
    agents: list[AgentType], domains: list[WorkDomain], tasks: list[str], mode: SetupMode,
) -> InterviewAnswer:
    return InterviewAnswer(agents=agents, domains=domains, tasks=tasks, mode=mode)


def run_interview(detected: list[AgentInstallation] | None = None) -> InterviewAnswer:
    if not sys.stdin.isatty():
        raise RuntimeError(
            "the setup interview requires a TTY; run 'grayom doctor' in automation or use a terminal"
        )
    detected_map = {item.agent: item.detected for item in detected or []}
    agent_choices = []
    for agent, label in (
        (AgentType.CODEX, "Codex"), (AgentType.CLAUDE_CODE, "Claude Code"), (AgentType.CURSOR, "Cursor"),
    ):
        # InquirerPy's checkbox has no 'disabled' option, so an Agent that is not installed is
        # withheld from the list instead of being offered as an unselectable entry.
        if detected and not detected_map.get(agent, False):
            continue
        agent_choices.append(
            {"name": label, "value": agent, "enabled": bool(detected_map.get(agent, False))}
        )
    if not agent_choices:
        raise RuntimeError("no supported Agent was detected; GrayOM does not install Agents")
    agents = inquirer.checkbox(
        message="Select AI Agents:", choices=agent_choices,
        validate=lambda value: bool(value), invalid_message="Select at least one Agent",
    ).execute()
    domains = inquirer.checkbox(
        message="Select Work Domains:",
        choices=[{"name": label, "value": value} for label, value in DOMAIN_LABELS.items()],
        validate=lambda value: bool(value), invalid_message="Select at least one domain",
    ).execute()
    tasks: list[str] = []
    for domain in domains:
        choices = TASKS.get(domain, [])
        if choices:
            tasks.extend(inquirer.checkbox(
                message=f"Select tasks for {domain.value.replace('_', ' ').title()}:",
                choices=[{"name": task.replace("_", " ").title(), "value": task} for task in choices],
            ).execute())
    mode = inquirer.select(
        message="Configuration mode:",
        choices=[{"name": "Minimal", "value": SetupMode.MINIMAL}, {"name": "Performance", "value": SetupMode.PERFORMANCE}],
    ).execute()
    return build_answer(agents, domains, tasks, mode)
