from InquirerPy import inquirer

from grayom_agent_guidance.models import AgentType, InterviewAnswer, SetupMode, WorkDomain


DOMAIN_LABELS = {domain.value.replace("_", " ").title(): domain for domain in WorkDomain}
TASKS = {
    WorkDomain.WEB_DEVELOPMENT: ["frontend", "backend", "full_stack", "api_development", "testing", "code_review", "performance_optimization", "security_review"],
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: ["source_code_analysis", "security_report_automation"],
    WorkDomain.VULNERABILITY_RESEARCH: ["oss_vulnerability_research", "cve_analysis", "patch_analysis", "supply_chain_security", "ai_llm_security"],
    WorkDomain.OSINT: ["osint_recon"],
    WorkDomain.AI_AGENT_DEVELOPMENT: ["coding_agent", "research_agent", "security_agent", "browser_agent", "data_agent", "multi_agent", "mcp_based_agent", "rag_agent"],
}


def run_interview() -> InterviewAnswer:
    agents = inquirer.checkbox(
        message="Select AI Agents:", choices=[{"name": "Codex", "value": AgentType.CODEX}],
        validate=lambda value: bool(value) or "Select at least one Agent",
    ).execute()
    domains = inquirer.checkbox(
        message="Select Work Domains:",
        choices=[{"name": label, "value": value} for label, value in DOMAIN_LABELS.items()],
        validate=lambda value: bool(value) or "Select at least one domain",
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
    return InterviewAnswer(agents=agents, domains=domains, tasks=tasks, mode=mode)

