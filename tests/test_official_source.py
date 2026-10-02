import asyncio
import httpx

from agent_guidance.core import recommend
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InterviewAnswer, SetupMode,
    SourceType, TrustMetadata, WorkDomain,
)
from agent_guidance.sources.official import OfficialSource
from agent_guidance.sources.validator import ComponentValidator


def test_official_catalog_is_scoped_to_selected_agent() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "resources": {"core": {"remaining": 50}},
        })),
        base_url="https://api.github.com",
    )
    source = OfficialSource(
        validator=ComponentValidator({AgentType.CODEX}), selected_agents={AgentType.CODEX}, client=client,
    )
    candidates = asyncio.run(source.search([]))
    asyncio.run(client.aclose())
    names = {item.repository_full_name for item in candidates}
    assert "github/github-mcp-server" in names
    assert "openai/skills" in names
    assert "anthropics/skills" not in names
    assert all(item.official_hint for item in candidates)


def test_official_duplicate_is_preferred() -> None:
    def component(identifier: str, official: bool) -> Component:
        return Component(
            id=identifier, name=identifier, type=ComponentType.MCP,
            github_url=f"https://github.com/example/{identifier}",
            supported_agents={AgentType.CODEX}, capabilities={Capability.REPOSITORY_ACCESS},
            trust=TrustMetadata(
                source_type=SourceType.OFFICIAL if official else SourceType.GITHUB,
                official=official, verified=True, verification_reason="test",
            ),
        )
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.GENERAL_DEVELOPMENT], mode=SetupMode.MINIMAL,
    )
    plan = recommend(answer, [component("community", False), component("official", True)])
    assert [item.id for item in plan.selected] == ["official"]
    skipped = next(item for item in plan.items if item.component.id == "community")
    assert "Official implementation" in skipped.reasons[0]
