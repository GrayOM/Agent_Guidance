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
