import asyncio

import httpx

from grayom_agent_guidance.core.discovery import discover_components
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InterviewAnswer, SetupMode,
    SourceType, TrustMetadata, WorkDomain,
)
from grayom_agent_guidance.sources.cache import CandidateCache


def cached_component() -> Component:
    return Component(
        id="new-cached-skill", name="New Cached Skill", type=ComponentType.SKILL,
        github_url="https://github.com/example/new-cached-skill",
        supported_agents={AgentType.CODEX}, capabilities={Capability.SOURCE_ANALYSIS},
        trust=TrustMetadata(
            source_type=SourceType.GITHUB, verified=True,
            verification_reason="repository structure validated",
        ),
    )


def answer() -> InterviewAnswer:
    return InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.SECURITY_TOOL_DEVELOPMENT],
        tasks=["source_code_analysis"], mode=SetupMode.MINIMAL,
    )


def test_offline_fallback_uses_registry_and_verified_cache(tmp_path) -> None:
    path = tmp_path / "cache.json"
    cache = CandidateCache(path=path)
    cache.put(cached_component(), "github", "v1")
    cache.save()
    result = asyncio.run(discover_components(answer(), offline=True, cache_path=path))
    ids = {item.id for item in result.candidates}
    assert result.offline_fallback
    assert "new-cached-skill" in ids
    assert "trailofbits-skills" in ids


def test_github_api_failure_gracefully_falls_back(tmp_path) -> None:
    path = tmp_path / "cache.json"
    cache = CandidateCache(path=path)
    cache.put(cached_component(), "github", "v1")
    cache.save()

    def handler(request):
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "limited"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    result = asyncio.run(discover_components(answer(), cache_path=path, github_client=client))
    asyncio.run(client.aclose())
    assert result.offline_fallback
    assert any("unavailable" in warning for warning in result.warnings)
    assert any(item.id == "new-cached-skill" for item in result.candidates)
