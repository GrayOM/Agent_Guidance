import asyncio

import httpx
import pytest

from grayom_agent_guidance.models import AgentType, Capability, ComponentType
from grayom_agent_guidance.sources.base import SourceUnavailable
from grayom_agent_guidance.sources.cache import CandidateCache
from grayom_agent_guidance.sources.github import GitHubSource
from grayom_agent_guidance.sources.validator import ComponentValidator


def github_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    headers = {"x-ratelimit-remaining": "42"}
    if path == "/rate_limit":
        return httpx.Response(200, headers=headers, json={
            "resources": {"search": {"remaining": 42}, "core": {"remaining": 42}},
        })
    if path == "/search/repositories":
        return httpx.Response(200, headers=headers, json={"items": [{
            "full_name": "example/security-skill",
            "html_url": "https://github.com/example/security-skill",
            "private": False, "pushed_at": "2026-09-20T00:00:00Z",
        }]})
    if path == "/repos/example/security-skill":
        return httpx.Response(200, headers=headers, json={
            "name": "security-skill", "full_name": "example/security-skill",
            "html_url": "https://github.com/example/security-skill",
            "description": "Codex source code analysis and vulnerability research",
            "default_branch": "main", "pushed_at": "2026-09-20T00:00:00Z",
            "stargazers_count": 50, "forks_count": 4, "archived": False,
            "license": {"spdx_id": "MIT"},
        })
    if path.endswith("/readme"):
        return httpx.Response(200, headers=headers, text="Codex source code analysis and vulnerability research skill")
    if path.endswith("/commits/main"):
        return httpx.Response(200, headers=headers, json={"sha": "deadbeef"})
    if path.endswith("/releases/latest"):
        return httpx.Response(404, headers=headers, json={"message": "not found"})
    if path.endswith("/git/trees/main"):
        return httpx.Response(200, headers=headers, json={
            "tree": [{"path": "SKILL.md", "type": "blob"}],
        })
    if path.endswith("/contents/SKILL.md"):
        return httpx.Response(200, headers=headers, text="---\nname: sec\ndescription: security\n---\n")
    raise AssertionError(f"unexpected request: {request.url}")


def test_github_source_discovers_and_validates_new_candidate(tmp_path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(github_handler), base_url="https://api.github.com",
    )
    source = GitHubSource(
        validator=ComponentValidator({AgentType.CODEX}),
        cache=CandidateCache(path=tmp_path / "cache.json"), client=client,
    )
    result = asyncio.run(source.discover(["codex security skill"]))
    asyncio.run(client.aclose())
    assert result.discovered == 1 and result.validated == 1
    candidate = result.candidates[0]
    assert candidate.type == ComponentType.SKILL
    assert Capability.SOURCE_ANALYSIS in candidate.capabilities
    assert candidate.install_method.ref == "deadbeef"
    assert result.rate_limit_remaining == 42


def test_github_rate_limit_is_reported() -> None:
    def handler(request):
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    source = GitHubSource(validator=ComponentValidator(), client=client)
    with pytest.raises(SourceUnavailable, match="rate limit reached") as error:
        asyncio.run(source.search(["query"]))
    asyncio.run(client.aclose())
    assert "remaining=0" in str(error.value)
    assert "denied access" not in str(error.value), "an exhausted limit is not an access decision"


def test_github_token_is_not_exposed_in_errors_or_logs(monkeypatch, caplog) -> None:
    secret = "ghp_super_secret_value"
    monkeypatch.setenv("GITHUB_TOKEN", secret)

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {secret}"
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "denied"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    source = GitHubSource(validator=ComponentValidator(), client=client)
    with pytest.raises(SourceUnavailable) as error:
        asyncio.run(source.search(["query"]))
    asyncio.run(client.aclose())
    assert secret not in str(error.value)
    assert secret not in caplog.text
