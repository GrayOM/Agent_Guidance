from agent_guidance.models import Capability, InterviewAnswer, WorkDomain


# A domain contributes only what is true of everyone working in it. Anything that depends on
# how the person works belongs in a detailed task below, so the selected tasks are what makes
# one profile differ from another. Before this, DevOps and mobile development produced an
# identical capability set and therefore an identical recommendation.
DOMAIN_CAPABILITIES: dict[WorkDomain, set[Capability]] = {
    WorkDomain.GENERAL_DEVELOPMENT: {
        Capability.PLANNING, Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW,
        Capability.REPOSITORY_ACCESS, Capability.TESTING, Capability.CODE_REVIEW,
        Capability.DEBUGGING, Capability.REFACTORING,
    },
    WorkDomain.WEB_DEVELOPMENT: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING, Capability.CODE_REVIEW,
    },
    WorkDomain.MOBILE_DEVELOPMENT: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING, Capability.CI_CD,
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
    # Differs from VULNERABILITY_RESEARCH deliberately: that domain reads source and
    # advisories, this one exercises a running target, so WEB_SECURITY_TESTING replaces
    # SOURCE_ANALYSIS in the base. Reporting is in both because the deliverable is a report.
    WorkDomain.PENETRATION_TESTING: {
        Capability.WEB_SECURITY_TESTING, Capability.SECURITY_ANALYSIS,
        Capability.VULNERABILITY_RESEARCH, Capability.NETWORK_ACCESS, Capability.REPORTING,
    },
    WorkDomain.OSINT: {
        Capability.NETWORK_ACCESS, Capability.BROWSER_AUTOMATION, Capability.REPORTING,
        Capability.WEB_RESEARCH,
    },
    WorkDomain.DEVOPS: {
        Capability.CODE_EDITING, Capability.DEVELOPMENT_WORKFLOW, Capability.REPOSITORY_ACCESS,
        Capability.TESTING, Capability.CI_CD, Capability.OBSERVABILITY,
    },
    WorkDomain.DATA_ANALYSIS: {
        Capability.DATA_ANALYSIS, Capability.REPORTING, Capability.DATABASE_ACCESS,
    },
    WorkDomain.RESEARCH_WRITING: {
        Capability.NETWORK_ACCESS, Capability.REPORTING, Capability.WEB_RESEARCH,
        Capability.DOCUMENT_AUTHORING,
    },
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
    # General development
    "feature_implementation": {Capability.CODE_EDITING, Capability.PLANNING},
    # SOURCE_ANALYSIS is Agent Guidance's static-analysis vocabulary, so it would surface SAST
    # tooling here rather than a debugger or a way to read the failing code.
    "bug_investigation": {Capability.DEBUGGING, Capability.REPOSITORY_ACCESS},
    "refactoring": {Capability.REFACTORING, Capability.CODE_EDITING},
    "dependency_upgrade": {Capability.DEPENDENCY_MANAGEMENT, Capability.REPOSITORY_ACCESS},
    "api_integration": {Capability.API_INTEGRATION, Capability.CODE_EDITING},
    "documentation": {Capability.DOCUMENT_AUTHORING, Capability.REPORTING},
    "project_planning": {Capability.PLANNING, Capability.DEVELOPMENT_WORKFLOW},
    "test_automation": {Capability.TESTING, Capability.TEST_EXECUTION},
    # Mobile development
    "ios_app": {Capability.MOBILE_IOS, Capability.CODE_EDITING},
    "android_app": {Capability.MOBILE_ANDROID, Capability.CODE_EDITING},
    "cross_platform_app": {Capability.CROSS_PLATFORM, Capability.CODE_EDITING},
    "mobile_testing": {Capability.TESTING, Capability.TEST_EXECUTION},
    "app_release": {Capability.CI_CD, Capability.DEVELOPMENT_WORKFLOW},
    "mobile_backend_integration": {Capability.API_INTEGRATION, Capability.CLOUD_PLATFORM},
    # DevOps
    "ci_cd_pipeline": {Capability.CI_CD, Capability.DEVELOPMENT_WORKFLOW},
    "container_build": {Capability.CONTAINERIZATION, Capability.CI_CD},
    "kubernetes_operations": {Capability.ORCHESTRATION, Capability.CONTAINERIZATION},
    "infrastructure_as_code": {Capability.INFRASTRUCTURE_AS_CODE, Capability.CLOUD_PLATFORM},
    "monitoring_observability": {Capability.OBSERVABILITY, Capability.REPORTING},
    "cloud_resource_management": {Capability.CLOUD_PLATFORM, Capability.INFRASTRUCTURE_AS_CODE},
    "secrets_and_config": {Capability.CLOUD_PLATFORM, Capability.INFRASTRUCTURE_AS_CODE},
    "release_automation": {Capability.CI_CD, Capability.REPOSITORY_ACCESS},
    # Data analysis
    "data_exploration": {Capability.DATA_ANALYSIS, Capability.DATABASE_ACCESS},
    "sql_and_database": {Capability.DATABASE_ACCESS, Capability.DATA_ANALYSIS},
    "data_pipeline": {Capability.DATA_PIPELINE, Capability.DATABASE_ACCESS},
    "data_visualization": {Capability.DATA_VISUALIZATION, Capability.REPORTING},
    "reporting_automation": {Capability.REPORTING, Capability.DOCUMENT_AUTHORING},
    "notebook_workflow": {Capability.DATA_ANALYSIS, Capability.CODE_EDITING},
    # Research and writing
    "web_research": {Capability.WEB_RESEARCH, Capability.NETWORK_ACCESS},
    "document_drafting": {Capability.DOCUMENT_AUTHORING, Capability.REPORTING},
    "technical_documentation": {Capability.DOCUMENT_AUTHORING, Capability.REPOSITORY_ACCESS},
    "knowledge_base": {Capability.KNOWLEDGE_MANAGEMENT, Capability.DOCUMENT_AUTHORING},
    "source_collection": {Capability.WEB_RESEARCH, Capability.BROWSER_AUTOMATION},
    # Security tool development
    "scanner_development": {Capability.SECURITY_ANALYSIS, Capability.CODE_EDITING},
    "exploit_tooling": {Capability.VULNERABILITY_RESEARCH, Capability.CODE_EDITING},
    "security_ci_integration": {Capability.CI_CD, Capability.SECURITY_ANALYSIS},
    # Penetration testing and vulnerability assessment. Each task names the tool class the
    # phase actually needs: a request forger for authorisation work, a database client to
    # confirm an injection, a browser driver for session handling.
    "web_application_assessment": {
        Capability.WEB_SECURITY_TESTING, Capability.SECURITY_ANALYSIS,
    },
    "authentication_testing": {
        Capability.WEB_SECURITY_TESTING, Capability.BROWSER_AUTOMATION,
    },
    # Forging a request to reach another user's object uses the same intercepting proxy as
    # the rest of the assessment. Adding API_INTEGRATION here matched tooling for *building*
    # an API client, which recommended an Agent SDK plugin for authorisation testing.
    "authorization_testing": {Capability.WEB_SECURITY_TESTING},
    "injection_testing": {Capability.WEB_SECURITY_TESTING, Capability.DATABASE_ACCESS},
    # API_INTEGRATION earns its place here: an API assessment starts from the spec.
    "api_security_testing": {Capability.WEB_SECURITY_TESTING, Capability.API_INTEGRATION},
    "mobile_application_assessment": {
        Capability.WEB_SECURITY_TESTING, Capability.MOBILE_ANDROID, Capability.MOBILE_IOS,
    },
    # Reading the target's source as a diagnosis, which is where SAST tooling belongs. It is
    # a phase of an assessment here, not the tool-building work that owns the other table.
    "secure_code_review": {Capability.SOURCE_ANALYSIS, Capability.SECURITY_ANALYSIS},
    "infrastructure_testing": {Capability.NETWORK_ACCESS, Capability.SECURITY_ANALYSIS},
    # Checklist work, not attack work: a baseline review of servers, network gear and
    # databases asks for benchmark runners rather than for exploitation tooling.
    "configuration_assessment": {
        Capability.CONFIGURATION_AUDIT, Capability.SECURITY_ANALYSIS,
    },
    "cloud_configuration_assessment": {
        Capability.CONFIGURATION_AUDIT, Capability.CLOUD_PLATFORM,
    },
    # Reproduction is the evidence a report stands on, so it asks for the vulnerability
    # vocabulary and the write-up, not for offensive tooling.
    "finding_reproduction": {Capability.VULNERABILITY_RESEARCH, Capability.REPORTING},
    "assessment_reporting": {Capability.REPORTING, Capability.DOCUMENT_AUTHORING},
    "retest_verification": {
        Capability.WEB_SECURITY_TESTING, Capability.VULNERABILITY_RESEARCH,
    },
    # OSINT
    "asset_discovery": {Capability.NETWORK_ACCESS, Capability.WEB_RESEARCH},
    "social_media_research": {Capability.WEB_RESEARCH, Capability.BROWSER_AUTOMATION},
    "breach_data_analysis": {Capability.DATA_ANALYSIS, Capability.NETWORK_ACCESS},
    "osint_reporting": {Capability.REPORTING, Capability.DOCUMENT_AUTHORING},
}


def infer_capabilities(answer: InterviewAnswer) -> set[Capability]:
    result: set[Capability] = set()
    for domain in answer.domains:
        result.update(DOMAIN_CAPABILITIES.get(domain, set()))
    for task in answer.tasks:
        result.update(TASK_CAPABILITIES.get(task, set()))
    return result


def infer_task_capabilities(answer: InterviewAnswer) -> set[Capability]:
    """Only what the detailed task answers asked for.

    A domain contributes a base that is true of everyone in it, so when the request budget
    forces a choice, the capabilities the person selected explicitly come first: a mobile
    developer who picked iOS and cross-platform should be searched for those before the
    CI/CD every mobile domain implies.
    """
    result: set[Capability] = set()
    for task in answer.tasks:
        result.update(TASK_CAPABILITIES.get(task, set()))
    return result
