from enum import StrEnum


class Capability(StrEnum):
    """What a component lets an Agent do.

    Every value must be reachable from the interview, searchable on GitHub and inferable
    from a repository's own text, or a user can select work that nothing can ever satisfy.
    `tests/test_capability_wiring.py` holds all three to the enum.
    """

    # Shared engineering work
    PLANNING = "planning"
    CODE_EDITING = "code_editing"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"
    TESTING = "testing"
    TEST_EXECUTION = "test_execution"
    DEVELOPMENT_WORKFLOW = "development_workflow"
    REPOSITORY_ACCESS = "repository_access"
    DEPENDENCY_MANAGEMENT = "dependency_management"
    API_INTEGRATION = "api_integration"

    # Security and vulnerability work
    SECURITY_ANALYSIS = "security_analysis"
    SOURCE_ANALYSIS = "source_analysis"
    VULNERABILITY_RESEARCH = "vulnerability_research"
    AI_VULNERABILITY_ANALYSIS = "ai_vulnerability_analysis"
    # Testing a running target rather than reading its source. SECURITY_ANALYSIS and
    # SOURCE_ANALYSIS both surface SAST tooling, which is the wrong tool class for someone
    # assessing a deployed application they did not write.
    WEB_SECURITY_TESTING = "web_security_testing"
    # Checking a target's settings against a baseline, which neither reads its source nor
    # attacks it: CIS benchmarks, hardening guides, cloud posture. The tools are checklist
    # runners, so neither the SAST nor the dynamic-testing vocabulary reaches them.
    CONFIGURATION_AUDIT = "configuration_audit"

    # Delivery and operations
    CI_CD = "ci_cd"
    CONTAINERIZATION = "containerization"
    ORCHESTRATION = "orchestration"
    INFRASTRUCTURE_AS_CODE = "infrastructure_as_code"
    OBSERVABILITY = "observability"
    CLOUD_PLATFORM = "cloud_platform"

    # Mobile
    MOBILE_IOS = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    CROSS_PLATFORM = "cross_platform"

    # Data
    DATA_ANALYSIS = "data_analysis"
    DATABASE_ACCESS = "database_access"
    DATA_PIPELINE = "data_pipeline"
    DATA_VISUALIZATION = "data_visualization"

    # Research, reporting and knowledge
    NETWORK_ACCESS = "network_access"
    BROWSER_AUTOMATION = "browser_automation"
    WEB_RESEARCH = "web_research"
    DOCUMENT_AUTHORING = "document_authoring"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    REPORTING = "reporting"

    # Agent construction
    AGENT_DEVELOPMENT = "agent_development"
