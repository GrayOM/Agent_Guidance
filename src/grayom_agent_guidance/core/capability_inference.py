from grayom_agent_guidance.models import Capability, InterviewAnswer, WorkDomain


DOMAIN_CAPABILITIES: dict[WorkDomain, set[Capability]] = {
    WorkDomain.GENERAL_DEVELOPMENT: {
        Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TEST_EXECUTION, Capability.CODE_REVIEW,
    },
    WorkDomain.WEB_DEVELOPMENT: {
        Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TEST_EXECUTION, Capability.CODE_REVIEW,
    },
    WorkDomain.MOBILE_DEVELOPMENT: {
        Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TEST_EXECUTION,
    },
    WorkDomain.AI_AGENT_DEVELOPMENT: {
        Capability.AGENT_DEVELOPMENT, Capability.REPOSITORY_ACCESS,
        Capability.TEST_EXECUTION,
    },
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: {
        Capability.DEVELOPMENT_WORKFLOW, Capability.SECURITY_ANALYSIS,
        Capability.SOURCE_ANALYSIS, Capability.TEST_EXECUTION, Capability.REPORT_SUPPORT,
    },
    WorkDomain.VULNERABILITY_RESEARCH: {
        Capability.VULNERABILITY_RESEARCH, Capability.SECURITY_ANALYSIS,
        Capability.SOURCE_ANALYSIS, Capability.NETWORK_ACCESS, Capability.REPORT_SUPPORT,
    },
    WorkDomain.OSINT: {
        Capability.NETWORK_ACCESS, Capability.BROWSER_AUTOMATION, Capability.REPORT_SUPPORT,
    },
    WorkDomain.DEVOPS: {
        Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TEST_EXECUTION,
    },
    WorkDomain.DATA_ANALYSIS: {Capability.DATA_ANALYSIS, Capability.REPORT_SUPPORT},
    WorkDomain.RESEARCH_WRITING: {Capability.NETWORK_ACCESS, Capability.REPORT_SUPPORT},
}

TASK_CAPABILITIES: dict[str, set[Capability]] = {
    "code_review": {Capability.CODE_REVIEW},
    "security_review": {Capability.SECURITY_ANALYSIS, Capability.SOURCE_ANALYSIS},
    "source_code_analysis": {Capability.SOURCE_ANALYSIS, Capability.SECURITY_ANALYSIS},
    "oss_vulnerability_research": {Capability.VULNERABILITY_RESEARCH, Capability.REPOSITORY_ACCESS},
    "cve_analysis": {Capability.VULNERABILITY_RESEARCH, Capability.NETWORK_ACCESS},
    "osint_recon": {Capability.NETWORK_ACCESS, Capability.BROWSER_AUTOMATION},
    "security_report_automation": {Capability.REPORT_SUPPORT},
    "mcp_based_agent": {Capability.AGENT_DEVELOPMENT},
}


def infer_capabilities(answer: InterviewAnswer) -> set[Capability]:
    result: set[Capability] = set()
    for domain in answer.domains:
        result.update(DOMAIN_CAPABILITIES.get(domain, set()))
    for task in answer.tasks:
        result.update(TASK_CAPABILITIES.get(task, set()))
    return result

