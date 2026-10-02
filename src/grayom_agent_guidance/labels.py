"""Written labels for everything the interview puts in front of a person.

Deriving a label from an identifier (`task.replace("_", " ").title()`) is what produced
"Osint Recon", "Ci Cd Pipeline", "Ios App" and "Ai Llm Security" in the only screen users
actually interact with. Capitalisation rules cannot recover an acronym or a product name from
a snake_case identifier, so each one is written out here instead, and
tests/test_labels.py fails when a domain or task ships without one.

The identifiers stay as they are: they are the keys of DOMAIN_CAPABILITIES and
TASK_CAPABILITIES and are written to state files, so renaming them would break both.
"""

from .models import WorkDomain


DOMAIN_LABELS: dict[WorkDomain, str] = {
    WorkDomain.GENERAL_DEVELOPMENT: "General development",
    WorkDomain.WEB_DEVELOPMENT: "Web development",
    WorkDomain.MOBILE_DEVELOPMENT: "Mobile development",
    WorkDomain.AI_AGENT_DEVELOPMENT: "AI Agent development",
    WorkDomain.SECURITY_TOOL_DEVELOPMENT: "Security tool development",
    WorkDomain.VULNERABILITY_RESEARCH: "Vulnerability research",
    WorkDomain.PENETRATION_TESTING: "Penetration testing and assessment",
    WorkDomain.OSINT: "OSINT",
    WorkDomain.DEVOPS: "DevOps",
    WorkDomain.DATA_ANALYSIS: "Data analysis",
    WorkDomain.RESEARCH_WRITING: "Research and writing",
}

TASK_LABELS: dict[str, str] = {
    # General development
    "feature_implementation": "Feature implementation",
    "bug_investigation": "Bug investigation",
    "refactoring": "Refactoring",
    "code_review": "Code review",
    "test_automation": "Test automation",
    "dependency_upgrade": "Dependency upgrades",
    "api_integration": "API integration",
    "documentation": "Documentation",
    "project_planning": "Project planning",
    # Web development
    "frontend": "Frontend",
    "backend": "Backend",
    "full_stack": "Full stack",
    "api_development": "API development",
    "testing": "Testing",
    "performance_optimization": "Performance optimisation",
    "security_review": "Security review",
    # Mobile development
    "ios_app": "iOS app",
    "android_app": "Android app",
    "cross_platform_app": "Cross-platform app",
    "mobile_testing": "Mobile testing",
    "app_release": "App release",
    "mobile_backend_integration": "Mobile backend integration",
    # AI Agent development
    "coding_agent": "Coding Agent",
    "research_agent": "Research Agent",
    "security_agent": "Security Agent",
    "browser_agent": "Browser automation Agent",
    "data_agent": "Data Agent",
    "multi_agent": "Multi-Agent orchestration",
    "mcp_based_agent": "MCP-based Agent",
    "rag_agent": "RAG Agent",
    # Security tool development
    "source_code_analysis": "Source code analysis tooling",
    "scanner_development": "Scanner development",
    "exploit_tooling": "Exploit tooling",
    "security_ci_integration": "Security CI/CD integration",
    "security_report_automation": "Security report automation",
    # Vulnerability research
    "oss_vulnerability_research": "Open-source vulnerability research",
    "cve_analysis": "CVE analysis",
    "patch_analysis": "Patch analysis",
    "supply_chain_security": "Supply chain security",
    "ai_llm_security": "AI and LLM security",
    "ai_vulnerability_analysis": "AI vulnerability analysis",
    # Penetration testing and assessment
    "web_application_assessment": "Web application assessment",
    "authentication_testing": "Authentication testing",
    "authorization_testing": "Authorisation testing",
    "injection_testing": "Injection testing",
    "api_security_testing": "API security testing",
    "mobile_application_assessment": "Mobile application assessment",
    "secure_code_review": "Secure code review",
    "infrastructure_testing": "Infrastructure testing",
    "configuration_assessment": "Configuration assessment",
    "cloud_configuration_assessment": "Cloud configuration assessment",
    "finding_reproduction": "Finding reproduction and PoC",
    "assessment_reporting": "Assessment reporting",
    "retest_verification": "Retest verification",
    # OSINT
    "osint_recon": "OSINT reconnaissance",
    "asset_discovery": "Asset discovery",
    "social_media_research": "Social media research",
    "breach_data_analysis": "Breach data analysis",
    "osint_reporting": "OSINT reporting",
    # DevOps
    "ci_cd_pipeline": "CI/CD pipelines",
    "container_build": "Container builds",
    "kubernetes_operations": "Kubernetes operations",
    "infrastructure_as_code": "Infrastructure as code",
    "monitoring_observability": "Monitoring and observability",
    "cloud_resource_management": "Cloud resource management",
    "secrets_and_config": "Secrets and configuration",
    "release_automation": "Release automation",
    # Data analysis
    "data_exploration": "Data exploration",
    "sql_and_database": "SQL and databases",
    "data_pipeline": "Data pipelines",
    "data_visualization": "Data visualisation",
    "reporting_automation": "Reporting automation",
    "notebook_workflow": "Notebook workflow",
    # Research and writing
    "web_research": "Web research",
    "source_collection": "Source collection",
    "document_drafting": "Document drafting",
    "technical_documentation": "Technical documentation",
    "knowledge_base": "Knowledge base",
}


def domain_label(domain: WorkDomain) -> str:
    return DOMAIN_LABELS[domain]


def task_label(task: str) -> str:
    """The written label for a task, falling back to the identifier made readable.

    A fallback rather than a KeyError because an identifier can also reach this from a state
    file written by an older version, where the task no longer exists in TASK_LABELS. The
    guard test is what keeps the fallback from being used for a task this version offers.
    """
    return TASK_LABELS.get(task) or task.replace("_", " ").capitalize()
