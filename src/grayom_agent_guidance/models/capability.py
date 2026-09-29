from enum import StrEnum


class Capability(StrEnum):
    DEVELOPMENT_WORKFLOW = "development_workflow"
    REPOSITORY_ACCESS = "repository_access"
    TEST_EXECUTION = "test_execution"
    CODE_REVIEW = "code_review"
    SECURITY_ANALYSIS = "security_analysis"
    SOURCE_ANALYSIS = "source_analysis"
    VULNERABILITY_RESEARCH = "vulnerability_research"
    NETWORK_ACCESS = "network_access"
    BROWSER_AUTOMATION = "browser_automation"
    REPORT_SUPPORT = "report_support"
    DATA_ANALYSIS = "data_analysis"
    AGENT_DEVELOPMENT = "agent_development"

