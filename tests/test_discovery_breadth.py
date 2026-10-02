"""Discovery has to be broad enough to be a recommendation rather than a sample.

These cover the three limits that kept live GitHub discovery from doing its job: a global
star ranking that crowded out specialised capabilities, a request budget that ignored
whether a token was present, and third-party Skills discarded for not naming an Agent.
"""

import asyncio

import httpx
import pytest

from agent_guidance.models import AgentType, ComponentType, SourceType
from agent_guidance.sources.base import RawCandidate
from agent_guidance.sources.budget import (
    CORE_LIMIT_PER_HOUR, SEARCH_LIMIT_PER_MINUTE, DiscoveryBudget,
)
from agent_guidance.sources.github import GitHubSource, _interleave
from agent_guidance.sources.normalizer import SKILL_FORMAT_NOTE, _supported_agents
from agent_guidance.sources.validator import ComponentValidator


def _raw(full_name: str, stars: int = 0) -> RawCandidate:
    return RawCandidate(
        repository_full_name=full_name, repository_url=f"https://github.com/{full_name}",
        source_type=SourceType.GITHUB, metadata={"stargazers_count": stars},
    )


# --- candidate selection -------------------------------------------------------------


def test_every_capability_query_reaches_the_plan_before_any_query_repeats() -> None:
    """A global star ranking gave all slots to the most popular query's results."""
    popular = [_raw("generic/one", 9000), _raw("generic/two", 8000), _raw("generic/three", 7000)]
    niche = [_raw("security/tool", 12)]

    selected = _interleave([popular, niche], limit=2)

    assert [item.repository_full_name for item in selected] == ["generic/one", "security/tool"]


def test_interleaving_still_fills_the_budget_when_a_query_returns_nothing() -> None:
    selected = _interleave([[], [_raw("a/one"), _raw("a/two")], []], limit=2)

    assert [item.repository_full_name for item in selected] == ["a/one", "a/two"]


def test_interleaving_never_exceeds_the_budget() -> None:
    buckets = [[_raw(f"owner{index}/repo{position}") for position in range(5)] for index in range(4)]

    assert len(_interleave(buckets, limit=3)) == 3
    assert _interleave(buckets, limit=0) == []
    assert _interleave([], limit=5) == []


def test_a_repository_matched_by_two_queries_is_offered_once() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"search": {"remaining": 100}}})
        return httpx.Response(200, json={"items": [
            {"full_name": "Shared/Repo", "html_url": "https://github.com/Shared/Repo",
             "stargazers_count": 5, "pushed_at": "2026-01-01T00:00:00Z"},
        ]})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    source = GitHubSource(validator=ComponentValidator(), client=client)
    found = asyncio.run(source.search(["security analysis", "vulnerability research"]))
    asyncio.run(client.aclose())

    assert [item.repository_full_name for item in found] == ["Shared/Repo"]


# --- request budget ------------------------------------------------------------------


@pytest.mark.parametrize("authenticated", [False, True])
def test_the_budget_stays_inside_the_github_limits_it_documents(authenticated: bool) -> None:
    budget = DiscoveryBudget.detect(authenticated=authenticated)

    assert budget.within_limits, (
        f"{budget.search_requests} searches (limit {SEARCH_LIMIT_PER_MINUTE[authenticated]}), "
        f"{budget.core_requests} core requests (limit {CORE_LIMIT_PER_HOUR[authenticated]})"
    )


def test_a_token_widens_discovery_and_its_absence_is_explained() -> None:
    anonymous = DiscoveryBudget.detect(authenticated=False)
    authenticated = DiscoveryBudget.detect(authenticated=True)

    assert authenticated.max_candidates > anonymous.max_candidates
    assert authenticated.search_queries_per_type > anonymous.search_queries_per_type
    assert "GITHUB_TOKEN" in (anonymous.advisory() or "")
    assert authenticated.advisory() is None


def test_the_budget_follows_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert DiscoveryBudget.detect().authenticated is False

    monkeypatch.setenv("GH_TOKEN", "x")
    assert DiscoveryBudget.detect().authenticated is True


def test_the_budget_caps_the_files_read_per_repository(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    source = GitHubSource(validator=ComponentValidator())

    assert source.budget.files_per_repository == 4
    assert source.max_candidates == source.budget.max_candidates


# --- third-party Skill recognition ---------------------------------------------------


def test_a_skill_that_names_no_agent_is_still_installable_everywhere() -> None:
    """Most community SKILL.md repositories never name an Agent; dropping them lost them."""
    agents, note = _supported_agents("a collection of useful skills", ["skills/x/SKILL.md"],
                                     ComponentType.SKILL)

    assert agents == {AgentType.CODEX, AgentType.CLAUDE_CODE}
    assert note == SKILL_FORMAT_NOTE


def test_an_agent_named_in_the_repository_still_wins_over_the_format_inference() -> None:
    agents, note = _supported_agents("built for claude code", [], ComponentType.SKILL)

    assert agents == {AgentType.CLAUDE_CODE}
    assert note is None


def test_the_format_inference_does_not_apply_to_mcp_servers() -> None:
    """An MCP server's transport is not implied by a Skill format, so it needs real evidence."""
    agents, note = _supported_agents("an mcp server", ["server.json"], ComponentType.MCP)

    assert agents == set()
    assert note is None
