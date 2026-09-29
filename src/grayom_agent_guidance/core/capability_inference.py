from grayom_agent_guidance.models import Capability, InterviewAnswer, WorkDomain


DOMAIN_CAPABILITIES: dict[WorkDomain, set[Capability]] = {
    WorkDomain.GENERAL_DEVELOPMENT: {
        Capability.PLANNING, Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW,
        Capability.REPOSITORY_ACCESS, Capability.TESTING, Capability.CODE_REVIEW,
    },
    WorkDomain.WEB_DEVELOPMENT: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING, Capability.CODE_REVIEW,
    },
    WorkDomain.MOBILE_DEVELOPMENT: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING,
    },
    WorkDomain.AI_AGENT_DEVELOPMENT: {
        Capability.AGENT_DEVELOPMENT, Capability.CODE_EDITING, Capability.REPOSITORY_ACCESS,
        Capability.TESTING,
    },
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.SECURITY_ANALYSIS, Capability.SOURCE_ANALYSIS, Capability.TESTING,
        Capability.REPORTING,
    },
    WorkDomain.VULNERABILITY_RESEARCH: {
        Capability.VULNERABILITY_RESEARCH, Capability.SECURITY_ANALYSIS,
        Capability.SOURCE_ANALYSIS, Capability.NETWORK_ACCESS, Capability.REPORTING,
    },
    WorkDomain.OSINT: {
        Capability.NETWORK_ACCESS, Capability.BROWSER_AUTOMATION, Capability.REPORTING,
    },
    WorkDomain.DEVOPS: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING,
    },
    WorkDomain.DATA_ANALYSIS: {Capability.DATA_ANALYSIS, Capability.REPORTING},
    WorkDomain.RESEARCH_WRITING: {Capability.NETWORK_ACCESS, Capability.REPORTING},
}

TASK_CAPABILITIES: dict[str, set[Capability]] = {
    "frontend": {Capability.CODE_EDITING, Capability.TESTING},
    "backend": {Capability.CODE_EDITING, Capability.REPOSITORY_ACCESS, Capability.TESTING},
    "full_stack": {Capability.CODE_EDITING, Capability.REPOSITORY_ACCESS, Capability.TESTING},
    "api_development": {Capability.CODE_EDITING, Capability.TESTING},
    "testing": {Capability.TESTING, Capability.TEST_EXECUTION},
    "performance_optimization": {Capability.CODE_EDITING, Capability.TESTING},
    "code_review": {Capability.CODE_REVIEW},
    "security_review": {Capability.SECURITY_ANALYSIS, Capability.SOURCE_ANALYSIS},
    "source_code_analysis": {Capability.SOURCE_ANALYSIS, Capability.SECURITY_ANALYSIS},
    "oss_vulnerability_research": {Capability.VULNERABILITY_RESEARCH, Capability.REPOSITORY_ACCESS},
    "cve_analysis": {Capability.VULNERABILITY_RESEARCH, Capability.NETWORK_ACCESS},
    "osint_recon": {Capability.NETWORK_ACCESS, Capability.BROWSER_AUTOMATION},
    "security_report_automation": {Capability.REPORTING},
    "mcp_based_agent": {Capability.AGENT_DEVELOPMENT},
    "coding_agent": {Capability.AGENT_DEVELOPMENT, Capability.CODE_EDITING, Capability.TESTING},
    "research_agent": {Capability.AGENT_DEVELOPMENT, Capability.NETWORK_ACCESS, Capability.REPORTING},
    "security_agent": {Capability.AGENT_DEVELOPMENT, Capability.SECURITY_ANALYSIS},
    "browser_agent": {Capability.AGENT_DEVELOPMENT, Capability.BROWSER_AUTOMATION, Capability.NETWORK_ACCESS},
    "data_agent": {Capability.AGENT_DEVELOPMENT, Capability.DATA_ANALYSIS},
    "multi_agent": {Capability.AGENT_DEVELOPMENT, Capability.PLANNING},
    "rag_agent": {Capability.AGENT_DEVELOPMENT, Capability.REPOSITORY_ACCESS, Capability.DATA_ANALYSIS},
    "patch_analysis": {Capability.VULNERABILITY_RESEARCH, Capability.SOURCE_ANALYSIS},
    "supply_chain_security": {Capability.SECURITY_ANALYSIS, Capability.REPOSITORY_ACCESS},
    "ai_llm_security": {Capability.AI_VULNERABILITY_ANALYSIS, Capability.SECURITY_ANALYSIS},
    "ai_vulnerability_analysis": {
        Capability.AI_VULNERABILITY_ANALYSIS, Capability.SECURITY_ANALYSIS,
        Capability.VULNERABILITY_RESEARCH,
    },
}


def infer_capabilities(answer: InterviewAnswer) -> set[Capability]:
    result: set[Capability] = set()
    for domain in answer.domains:
        result.update(DOMAIN_CAPABILITIES.get(domain, set()))
    for task in answer.tasks:
        result.update(TASK_CAPABILITIES.get(task, set()))
    return result
