from grayom_agent_guidance.models import AgentType, Capability, ComponentType


CAPABILITY_TERMS: dict[Capability, str] = {
    Capability.SECURITY_ANALYSIS: "security analysis",
    Capability.SOURCE_ANALYSIS: "source code analysis",
    Capability.VULNERABILITY_RESEARCH: "vulnerability research",
    Capability.REPOSITORY_ACCESS: "repository",
    Capability.TESTING: "testing",
    Capability.CODE_EDITING: "coding",
    Capability.CODE_REVIEW: "code review",
    Capability.BROWSER_AUTOMATION: "browser automation",
    Capability.DATA_ANALYSIS: "data analysis",
    Capability.REPORTING: "reporting",
    Capability.AGENT_DEVELOPMENT: "agent development",
    Capability.AI_VULNERABILITY_ANALYSIS: "LLM security",
    Capability.NETWORK_ACCESS: "OSINT",
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
) -> list[str]:
    agent_terms = " OR ".join(sorted(agent.value.replace("_", " ") for agent in agents))
    capability_terms = [CAPABILITY_TERMS[item] for item in sorted(capabilities, key=lambda item: item.value) if item in CAPABILITY_TERMS]
    queries: list[str] = []
    for term in capability_terms[: max(1, limit - 1)]:
        queries.append(f'"{term}" "{TYPE_TERMS[component_type]}" {agent_terms}')
    queries.append(f'"{TYPE_TERMS[component_type]}" {agent_terms}')
    return list(dict.fromkeys(queries))[:limit]
