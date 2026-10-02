from grayom_agent_guidance.models import AgentType, Capability, ComponentType


# Declaration order is the search priority: when the request budget forces truncation, the
# specialised capabilities are searched before the generic ones. Alphabetical order would drop
# exactly the terms a specialised profile is asking about, and the generic ones are already
# covered by the untargeted query every component type gets.
CAPABILITY_TERMS: dict[Capability, str] = {
    # Specialised: an untargeted query will not surface these.
    Capability.AI_VULNERABILITY_ANALYSIS: "LLM security",
    Capability.VULNERABILITY_RESEARCH: "vulnerability research",
    Capability.WEB_SECURITY_TESTING: "web application security testing",
    Capability.SECURITY_ANALYSIS: "security analysis",
    Capability.SOURCE_ANALYSIS: "source code analysis",
    Capability.ORCHESTRATION: "kubernetes",
    Capability.INFRASTRUCTURE_AS_CODE: "terraform infrastructure as code",
    Capability.CI_CD: "CI/CD pipeline",
    Capability.OBSERVABILITY: "observability monitoring",
    Capability.CONTAINERIZATION: "docker container",
    Capability.CLOUD_PLATFORM: "cloud platform",
    Capability.MOBILE_IOS: "iOS Swift",
    Capability.MOBILE_ANDROID: "Android Kotlin",
    Capability.CROSS_PLATFORM: "React Native Flutter",
    Capability.DATA_PIPELINE: "data pipeline ETL",
    Capability.DATABASE_ACCESS: "database SQL",
    Capability.DATA_VISUALIZATION: "data visualization",
    Capability.BROWSER_AUTOMATION: "browser automation",
    Capability.WEB_RESEARCH: "web search research",
    Capability.KNOWLEDGE_MANAGEMENT: "knowledge base notes",
    Capability.DOCUMENT_AUTHORING: "document writing",
    Capability.AGENT_DEVELOPMENT: "agent development",
    Capability.DATA_ANALYSIS: "data analysis",
    Capability.NETWORK_ACCESS: "OSINT",
    Capability.REPORTING: "reporting",
    Capability.API_INTEGRATION: "API integration",
    Capability.DEPENDENCY_MANAGEMENT: "dependency management",
    # Generic engineering: the untargeted query already reaches these.
    Capability.DEBUGGING: "debugging",
    Capability.REFACTORING: "refactoring",
    Capability.TEST_EXECUTION: "test runner",
    Capability.CODE_REVIEW: "code review",
    Capability.REPOSITORY_ACCESS: "repository",
    Capability.TESTING: "testing",
    Capability.DEVELOPMENT_WORKFLOW: "development workflow",
    Capability.PLANNING: "planning",
    Capability.CODE_EDITING: "coding",
}


TYPE_TERMS = {
    ComponentType.SKILL: "agent skill SKILL.md",
    ComponentType.MCP: "MCP server",
    ComponentType.PLUGIN: "agent plugin",
}


def build_queries(
    agents: list[AgentType] | set[AgentType],
    capabilities: set[Capability],
    component_type: ComponentType,
    limit: int = 6,
    preferred: set[Capability] | None = None,
) -> list[str]:
    """Build bounded search queries, most specific first.

    `preferred` holds the capabilities the person selected explicitly rather than inherited
    from their work domain; they are searched first so a truncated budget does not spend its
    queries on the domain's generic base.
    """
    agent_terms = " OR ".join(sorted(agent.value.replace("_", " ") for agent in agents))
    preferred = preferred or set()
    selected = [
        (capability, term) for capability, term in CAPABILITY_TERMS.items()
        if capability in capabilities
    ]
    capability_terms = [
        term for capability, term in selected if capability in preferred
    ] + [
        term for capability, term in selected if capability not in preferred
    ]
    queries: list[str] = []
    for term in capability_terms[: max(1, limit - 1)]:
        queries.append(f'"{term}" "{TYPE_TERMS[component_type]}" {agent_terms}')
    queries.append(f'"{TYPE_TERMS[component_type]}" {agent_terms}')
    return list(dict.fromkeys(queries))[:limit]
