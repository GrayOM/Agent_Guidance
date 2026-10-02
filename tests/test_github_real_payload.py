"""Discovery driven by a repository object GitHub actually returned.

The other GitHub tests write their responses by hand, so they prove the code works against the
fields those tests chose to include. This one serves `tests/fixtures/github_repository.json`,
captured verbatim from `GET /repos/grayom/agent_guidance` (95 fields, public metadata of this
project's own repository, with the volatile counters and timestamps pinned). A search response
carries the same repository object as its items, so the fixture stands in for both.

What this closes and what it does not: every step from the HTTP response through paging,
normalisation, validation and recommendation runs here against real field shapes, so the only
part of live discovery left unexercised is the socket call itself. It is not a claim that
discovery has been run against api.github.com — the container this was written in has its
GitHub API access bound to one repository, and `GET /search/repositories` answers 403 with
"sessions are bound to their configured repositories".
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from grayom_agent_guidance.core.recommender import recommend
from grayom_agent_guidance.models import (
    AgentType, Capability, ComponentType, InterviewAnswer, SetupMode, WorkDomain,
)
from grayom_agent_guidance.sources.cache import CandidateCache
from grayom_agent_guidance.sources.github import GitHubSource
from grayom_agent_guidance.sources.validator import ComponentValidator


FIXTURE = Path(__file__).parent / "fixtures" / "github_repository.json"
SKILL_MD = (
    "---\n"
    "name: web-assessment\n"
    "description: Web application security assessment, injection testing and reporting\n"
    "---\n\n"
    "Covers authentication testing, injection testing and vulnerability research.\n"
)


@pytest.fixture(scope="module")
def repository() -> dict:
    return json.loads(FIXTURE.read_text())


def _handler(repository: dict, *, calls: list[str] | None = None):
    """Serve the real repository object from every endpoint that returns one."""
    full_name = repository["full_name"]
    headers = {"x-ratelimit-remaining": "4999"}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append(path)
        if path == "/rate_limit":
            return httpx.Response(200, headers=headers, json={
                "resources": {"search": {"remaining": 29}, "core": {"remaining": 4999}},
            })
        if path == "/search/repositories":
            # The real search payload wraps the same repository objects in these three keys.
            return httpx.Response(200, headers=headers, json={
                "total_count": 1, "incomplete_results": False, "items": [repository],
            })
        if path == f"/repos/{full_name}":
            return httpx.Response(200, headers=headers, json=repository)
        if path.endswith("/readme"):
            return httpx.Response(200, headers=headers, text=SKILL_MD)
        if path.endswith(f"/commits/{repository['default_branch']}"):
            return httpx.Response(200, headers=headers, json={"sha": "0f1e2d3c4b5a"})
        if path.endswith("/releases/latest"):
            return httpx.Response(404, headers=headers, json={"message": "Not Found"})
        if path.endswith(f"/git/trees/{repository['default_branch']}"):
            return httpx.Response(200, headers=headers, json={
                "tree": [
                    {"path": "SKILL.md", "type": "blob"},
                    {"path": "README.md", "type": "blob"},
                ],
            })
        if path.endswith("/contents/SKILL.md"):
            return httpx.Response(200, headers=headers, text=SKILL_MD)
        raise AssertionError(f"unexpected request: {request.url}")

    return handle


def _discover(repository: dict, tmp_path, calls: list[str] | None = None):
    """Run the real entry point: search, fetch, normalise, validate, cache."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler(repository, calls=calls)),
        base_url="https://api.github.com",
    )
    source = GitHubSource(
        validator=ComponentValidator({AgentType.CLAUDE_CODE}),
        cache=CandidateCache(path=tmp_path / "cache.json"), client=client,
    )
    try:
        return asyncio.run(source.discover(["security assessment skill"]))
    finally:
        asyncio.run(client.aclose())


def test_the_real_payload_is_the_one_github_returned(repository: dict) -> None:
    """A guard on the fixture: trimming it down would quietly weaken every test below."""
    assert repository["full_name"] == "GrayOM/Agent_Guidance"
    assert len(repository) >= 90, "the fixture was reduced to a hand-picked subset"
    for field in ("full_name", "html_url", "private", "pushed_at", "default_branch",
                  "stargazers_count", "forks_count", "archived", "license", "description"):
        assert field in repository, f"the code reads {field} and the fixture no longer has it"


def test_discovery_reads_a_real_repository_object_end_to_end(repository, tmp_path) -> None:
    result = _discover(repository, tmp_path)
    assert result.discovered == 1 and result.validated == 1
    component = result.candidates[0]

    # The id is derived from a real full_name, which is mixed case and carries an underscore.
    assert component.id == "grayom-agent_guidance"
    assert str(component.github_url) == repository["html_url"]
    assert component.type is ComponentType.SKILL
    assert component.install_method.ref == "0f1e2d3c4b5a"


def test_maintenance_metadata_comes_from_the_real_fields(repository, tmp_path) -> None:
    metadata = _discover(repository, tmp_path).candidates[0].maintenance_metadata
    assert metadata.stars == repository["stargazers_count"]
    assert metadata.forks == repository["forks_count"]
    assert metadata.license == repository["license"]["spdx_id"]
    assert metadata.archived is False
    # pushed_at is an ISO-8601 string with a Z suffix, which is the form that needed handling.
    assert str(metadata.last_commit).startswith("2026-09-28")


def test_a_capability_survives_from_the_real_payload_into_a_plan(repository, tmp_path) -> None:
    """The point of discovery: a repository GitHub described becomes something installable."""
    components = _discover(repository, tmp_path).candidates
    # Inferred from the SKILL.md text above, not asserted into existence: the recommender
    # has to be given a capability the interview below actually asks for.
    assert Capability.VULNERABILITY_RESEARCH in components[0].capabilities

    answer = InterviewAnswer(
        agents=[AgentType.CLAUDE_CODE],
        domains=[WorkDomain.PENETRATION_TESTING],
        tasks=["web_application_assessment"],
        mode=SetupMode.PERFORMANCE,
    )
    plan = recommend(answer, components)
    assert [component.id for component in plan.selected] == ["grayom-agent_guidance"]
    selected = [item for item in plan.items if item.selected]
    assert selected and selected[0].reasons, "a selection has to say why it was made"


def test_the_search_response_envelope_is_read_not_assumed(repository, tmp_path) -> None:
    """total_count and incomplete_results are present in a real payload and must be ignored."""
    calls: list[str] = []
    result = _discover(repository, tmp_path, calls=calls)
    assert "/rate_limit" in calls, "the search rate limit is checked before querying"
    assert calls.count("/search/repositories") >= 1
    assert result.validated == 1, "the envelope fields must not be mistaken for a result"


def test_a_private_repository_in_the_results_is_dropped(repository, tmp_path) -> None:
    """GitHub returns private repositories to an authorised token; installing one would fail."""
    result = _discover({**repository, "private": True}, tmp_path)
    assert result.discovered == 0 and result.candidates == []
