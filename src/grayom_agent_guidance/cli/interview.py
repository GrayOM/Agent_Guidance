import sys

from InquirerPy import inquirer

from grayom_agent_guidance.labels import domain_label, task_label
from grayom_agent_guidance.models import AgentInstallation, AgentType, InterviewAnswer, SetupMode, WorkDomain


DOMAIN_LABELS = {domain_label(domain): domain for domain in WorkDomain}

# Every domain needs detailed tasks: the domain alone only says what is true of everyone in
# it, so the selected tasks are what makes a recommendation specific to this person. A domain
# with no tasks asks one broad question and can only answer it as broadly.
# tests/test_capability_wiring.py keeps every domain populated and every task mapped.
TASKS: dict[WorkDomain, list[str]] = {
    WorkDomain.GENERAL_DEVELOPMENT: [
        "feature_implementation", "bug_investigation", "refactoring", "code_review",
        "test_automation", "dependency_upgrade", "api_integration", "documentation",
        "project_planning",
    ],
    WorkDomain.WEB_DEVELOPMENT: [
        "frontend", "backend", "full_stack", "api_development", "testing", "code_review",
        "performance_optimization", "security_review",
    ],
    WorkDomain.MOBILE_DEVELOPMENT: [
        "ios_app", "android_app", "cross_platform_app", "mobile_testing", "app_release",
        "mobile_backend_integration",
    ],
    WorkDomain.AI_AGENT_DEVELOPMENT: [
        "coding_agent", "research_agent", "security_agent", "browser_agent", "data_agent",
        "multi_agent", "mcp_based_agent", "rag_agent",
    ],
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: [
        "source_code_analysis", "scanner_development", "exploit_tooling",
        "security_ci_integration", "security_report_automation",
    ],
    WorkDomain.VULNERABILITY_RESEARCH: [
        "oss_vulnerability_research", "cve_analysis", "patch_analysis", "supply_chain_security",
        "ai_llm_security", "ai_vulnerability_analysis",
    ],
    # Assessing a target someone else built and deployed. This is not the same work as
    # SECURITY_TOOL_DEVELOPMENT (building the tools) or VULNERABILITY_RESEARCH (studying a
    # CVE or an upstream project), so it asks about the engagement's own phases.
    WorkDomain.PENETRATION_TESTING: [
        "web_application_assessment", "authentication_testing", "authorization_testing",
        "injection_testing", "api_security_testing", "mobile_application_assessment",
        "secure_code_review", "infrastructure_testing", "configuration_assessment",
        "cloud_configuration_assessment", "finding_reproduction", "assessment_reporting",
        "retest_verification",
    ],
    WorkDomain.OSINT: [
        "osint_recon", "asset_discovery", "social_media_research", "breach_data_analysis",
        "osint_reporting",
    ],
    WorkDomain.DEVOPS: [
        "ci_cd_pipeline", "container_build", "kubernetes_operations", "infrastructure_as_code",
        "monitoring_observability", "cloud_resource_management", "secrets_and_config",
        "release_automation",
    ],
    WorkDomain.DATA_ANALYSIS: [
        "data_exploration", "sql_and_database", "data_pipeline", "data_visualization",
        "reporting_automation", "notebook_workflow",
    ],
    WorkDomain.RESEARCH_WRITING: [
        "web_research", "source_collection", "document_drafting", "technical_documentation",
        "knowledge_base",
    ],
}


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
        (AgentType.CODEX, "Codex"), (AgentType.CLAUDE_CODE, "Claude Code"),
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
                message=f"Select tasks for {domain_label(domain)}:",
                choices=[{"name": task_label(task), "value": task} for task in choices],
            ).execute())
    mode = inquirer.select(
        message="Configuration mode:",
        choices=[{"name": "Minimal", "value": SetupMode.MINIMAL}, {"name": "Performance", "value": SetupMode.PERFORMANCE}],
    ).execute()
    return build_answer(agents, domains, tasks, mode)
