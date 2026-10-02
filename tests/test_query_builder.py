from agent_guidance.core.query_builder import build_queries
from agent_guidance.models import AgentType, Capability, ComponentType


def test_queries_are_capability_and_agent_aware_and_bounded() -> None:
    queries = build_queries(
        [AgentType.CODEX],
        {Capability.SECURITY_ANALYSIS, Capability.SOURCE_ANALYSIS, Capability.REPOSITORY_ACCESS},
        ComponentType.SKILL,
        limit=3,
    )
    assert len(queries) == 3
    assert all("codex" in query for query in queries)
    assert any("security analysis" in query or "source code analysis" in query for query in queries)
    assert all("SKILL.md" in query for query in queries)
