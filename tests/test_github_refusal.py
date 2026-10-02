"""GitHub refuses for three different reasons, and only one of them is worth waiting out.

Reporting every 403 as a rate limit sent a user with a scoped or expired token away for an
hour over something that would never change on its own. It happened in a real run: the
token was valid but scoped to one repository, and GrayOM said "rate limited" four times
while `remaining=unknown` sat in the same message as the evidence against it.
"""

import asyncio

import httpx
import pytest

from grayom_agent_guidance.models import AgentType, SourceType
from grayom_agent_guidance.sources.base import RawCandidate, SourceUnavailable
from grayom_agent_guidance.sources.budget import DiscoveryBudget
from grayom_agent_guidance.sources.github import GitHubSource, describe_refusal
from grayom_agent_guidance.sources.validator import ComponentValidator


def _response(status: int, headers: dict[str, str] | None = None, message: str = "") -> httpx.Response:
    return httpx.Response(
        status, headers=headers or {}, json={"message": message} if message else {},
    )


# --- which refusal is this -----------------------------------------------------------


def test_rejected_credentials_point_at_the_token() -> None:
    reason = describe_refusal(_response(401, message="Bad credentials"))

    assert "rejected the credentials" in reason
    assert "GITHUB_TOKEN" in reason
    assert "rate limit" not in reason.lower()


@pytest.mark.parametrize(
    ("status", "headers", "message"),
    [
        (429, {}, ""),
        (403, {"x-ratelimit-remaining": "0"}, ""),
        (403, {"retry-after": "60"}, ""),
        (403, {}, "API rate limit exceeded for user"),
    ],
)
def test_every_signal_github_uses_for_a_rate_limit_is_read_as_one(status, headers, message) -> None:
    reason = describe_refusal(_response(status, headers, message))

    assert "rate limit reached" in reason
    assert "denied access" not in reason


def test_a_retry_after_is_passed_on_so_the_user_knows_how_long() -> None:
    assert "retry after 60s" in describe_refusal(_response(403, {"retry-after": "60"}))


def test_a_forbidden_response_with_no_rate_limit_signal_is_an_access_decision() -> None:
    """This is the case that was being mislabelled; waiting does not fix it."""
    reason = describe_refusal(_response(
        403, {"x-ratelimit-remaining": "4999"},
        "GitHub access to this repository is not enabled for this session",
    ))

    assert "denied access rather than rate limiting" in reason
    assert "Waiting will not change this" in reason
    assert "scope" in reason and "SSO" in reason


def test_githubs_own_message_is_included_so_the_cause_is_not_guessed_at() -> None:
    reason = describe_refusal(_response(403, {}, "Resource protected by organization SAML"))

    assert "Resource protected by organization SAML" in reason


def test_a_refusal_without_a_json_body_still_explains_itself() -> None:
    reason = describe_refusal(httpx.Response(403, text="<html>no</html>"))

    assert "denied access" in reason
    assert "GitHub said" not in reason


def test_an_unauthorised_search_raises_rather_than_returning_nothing() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: _response(401, message="Bad credentials")),
        base_url="https://api.github.com",
    )
    source = GitHubSource(validator=ComponentValidator(), client=client)

    with pytest.raises(SourceUnavailable, match="rejected the credentials"):
        asyncio.run(source.search(["query"]))
    asyncio.run(client.aclose())


# --- one problem is reported once -----------------------------------------------------


def test_one_refusal_stopping_every_repository_is_reported_once() -> None:
    """Three repositories failing for one reason is one problem, not three warnings.

    The budget is pinned rather than detected: how many candidates a run keeps depends on
    whether a token is present, so leaving it to the environment would make this assert a
    different number on a machine that has one.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"search": {"remaining": 100}}})
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": [
                {"full_name": f"owner/repo{index}", "html_url": f"https://github.com/owner/repo{index}",
                 "stargazers_count": index, "pushed_at": "2026-01-01T00:00:00Z"}
                for index in range(3)
            ]})
        return _response(403, {}, "not enabled for this session")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    source = GitHubSource(
        validator=ComponentValidator({AgentType.CODEX}), client=client,
        budget=DiscoveryBudget.detect(authenticated=True),
    )
    assert source.max_candidates >= 3, "the budget must allow all three to be attempted"
    result = asyncio.run(source.discover(["query"]))
    asyncio.run(client.aclose())

    assert len(result.warnings) == 1, result.warnings
    assert result.warnings[0].startswith("3 repositories could not be read:")
    assert "denied access" in result.warnings[0]


def test_a_single_failing_repository_is_still_named() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"search": {"remaining": 100}}})
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": [
                {"full_name": "owner/only", "html_url": "https://github.com/owner/only",
                 "stargazers_count": 1, "pushed_at": "2026-01-01T00:00:00Z"},
            ]})
        return _response(403, {}, "not enabled")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    result = asyncio.run(
        GitHubSource(validator=ComponentValidator(), client=client).discover(["query"])
    )
    asyncio.run(client.aclose())

    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("owner/only:")


def test_distinct_failures_are_not_collapsed_into_one() -> None:
    """Grouping must be by cause, or two different problems look like one."""
    candidates = [
        RawCandidate(
            repository_full_name=f"owner/repo{index}",
            repository_url=f"https://github.com/owner/repo{index}",
            source_type=SourceType.GITHUB, metadata={},
        )
        for index in range(2)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "repo0" in str(request.url):
            return _response(403, {}, "not enabled")
        return _response(403, {"x-ratelimit-remaining": "0"}, "rate limit")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    source = GitHubSource(validator=ComponentValidator(), client=client)
    source.search = lambda queries: _ready(candidates)  # type: ignore[method-assign]
    result = asyncio.run(source.discover(["query"]))
    asyncio.run(client.aclose())

    assert len(result.warnings) == 2
    assert any("rate limit reached" in warning for warning in result.warnings)
    assert any("denied access" in warning for warning in result.warnings)


async def _ready(value):
    return value
