"""A discovered MCP server's launch command is a claim from its README until npm confirms it.

What this covers happened: a GitHub search returned `Sengtocxoen/sast-mcp`, whose install
method was scraped out of its README as `npx -y sast-mcp`, written to the user's Agent
configuration unpinned, and presented as verified with no risk line on the approval screen.
Three separate holes met there, and each has a test below:

  - the npm package name was never checked against the repository it was advertised under,
  - nothing was pinned, so npm's current latest ran at every Agent start,
  - the risk review had no rule for either, so the approval screen showed nothing.

The tests use a MockTransport so none of them reach the real registry; the one that proves
the GitHub token does not leak checks the request the resolver actually built.
"""

import asyncio

import httpx
import pytest

from agent_guidance.core.security import analyze_security
from agent_guidance.models import Component, ComponentType, InstallKind, InstallMethod
from agent_guidance.sources.base import RawCandidate
from agent_guidance.sources.normalizer import normalize_candidate
from agent_guidance.sources.npm import (
    _declared_repository, pin_npm_install, resolve_package, split_package_spec,
)
from agent_guidance.sources.validator import ComponentValidator


README = (
    "# server\n## Install\n```\n{command}\n```\n"
    "An MCP server that scans source code for vulnerabilities and writes findings reports.\n"
)


def raw(command: str, repository: str = "someone/mcp-server") -> RawCandidate:
    return RawCandidate(
        source="github", source_type="github", repository_full_name=repository,
        repository_url=f"https://github.com/{repository}",
        readme=README.format(command=command),
        metadata={"description": "security MCP server", "head_sha": "a" * 40,
                  "default_branch": "main", "stargazers_count": 3},
        files={},
    )


def registry(document, status: int = 200) -> httpx.AsyncClient:
    """A stand-in npm registry that answers every request with one document."""
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=document)),
    )


def pin(component: Component, repository: str, client: httpx.AsyncClient) -> Component:
    return ComponentValidator().validate(
        asyncio.run(pin_npm_install(component, repository_full_name=repository, client=client))
    )


# --- the version spec a README carries is not the name -------------------------------------

@pytest.mark.parametrize(("token", "expected"), [
    ("sast-mcp", ("sast-mcp", None)),
    ("sast-mcp@latest", ("sast-mcp", "latest")),
    ("sast-mcp@1.2.3", ("sast-mcp", "1.2.3")),
    # A scoped package's own leading @ is not a separator, or every scoped package would
    # resolve to the empty name and be refused.
    ("@scope/name", ("@scope/name", None)),
    ("@scope/name@2.0.0", ("@scope/name", "2.0.0")),
])
def test_split_package_spec(token, expected) -> None:
    assert split_package_spec(token) == expected


def test_the_name_reaching_the_registry_carries_no_version_spec() -> None:
    """`npx -y name@latest` scrapes as one token; asking npm for `name@latest` is a 404."""
    component = normalize_candidate(raw("npx -y sast-mcp@latest"))
    assert component.install_method.package == "sast-mcp"
    assert "@latest" not in " ".join(component.install_method.args)


# --- what the package says about where it comes from ---------------------------------------

@pytest.mark.parametrize(("field", "expected"), [
    ("https://github.com/owner/repo", "owner/repo"),
    ("git+https://github.com/Owner/Repo.git", "owner/repo"),
    ("github:owner/repo", "owner/repo"),
    ("owner/repo", "owner/repo"),
    ({"url": "git+ssh://git@github.com/owner/repo.git"}, "owner/repo"),
    # Not GitHub, so this check has nothing to say: reported as absent rather than guessed,
    # because a wrong match waves through the case the check exists to catch.
    ("https://gitlab.com/owner/repo", None),
    ("", None),
    (None, None),
])
def test_declared_repository(field, expected) -> None:
    assert _declared_repository({"repository": field} if field is not None else {}) == expected


# --- the three holes -----------------------------------------------------------------------

def test_a_resolved_package_is_pinned_into_the_args_that_get_written() -> None:
    """The pin has to land in args, because args is what goes into the Agent's config file."""
    client = registry({"name": "sast-mcp", "version": "1.4.2",
                       "repository": "https://github.com/someone/mcp-server"})
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert component.install_method.package_version == "1.4.2"
    assert component.install_method.args == ["-y", "sast-mcp@1.4.2"]
    assert component.recommendable


def test_a_package_naming_a_different_repository_is_refused() -> None:
    """The attack shape: a README advertising a package its repository does not own.

    Nothing connected GitHub repository ownership to npm package ownership before this, so a
    repository could be clean while its README pointed at anyone's package.
    """
    client = registry({"name": "@someone-else/other", "version": "9.9.9",
                       "repository": "https://github.com/someone-else/other"})
    component = pin(
        normalize_candidate(raw("npx -y @someone-else/other", "someone/mcp-server")),
        "someone/mcp-server", client,
    )

    assert not component.recommendable
    reason = " ".join(component.validation_warnings)
    assert "someone-else/other" in reason and "someone/mcp-server" in reason
    # Refused, and the args were left as they were rather than pinned to a package this
    # repository does not own.
    assert component.install_method.args == ["-y", "@someone-else/other"]


def test_a_package_that_does_not_exist_is_refused_with_that_reason() -> None:
    client = registry({"error": "Not found"}, status=404)
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert not component.recommendable
    assert "no package named sast-mcp" in " ".join(component.validation_warnings)


def test_an_unreachable_registry_refuses_rather_than_installing_unpinned() -> None:
    """A firewall is a reason not to offer the candidate, not a reason to skip the pin.

    This is the one place where being strict costs a user something real, and it is still the
    right answer: the alternative is writing `npx -y name` into their configuration, which is
    the behaviour being removed.
    """
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("npm unreachable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert not component.recommendable
    assert "npm could not be reached" in " ".join(component.validation_warnings)


def test_a_package_declaring_no_repository_is_offered_with_a_warning() -> None:
    """Publishing no repository field is common and not suspicious on its own."""
    client = registry({"name": "sast-mcp", "version": "1.0.0"})
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert component.recommendable
    assert component.install_method.package_version == "1.0.0"
    assert "declares no repository" in " ".join(component.validation_warnings)


# --- what is deliberately left alone -------------------------------------------------------

def test_a_registry_declared_server_is_not_touched() -> None:
    """The built-in registry declares its own install methods; only READMEs are in question.

    Without this the fix would quietly require npm for components that never involved it.
    """
    declared = Component(
        id="curated-mcp", name="Curated", type=ComponentType.MCP,
        github_url="https://github.com/owner/repo",
        install_method=InstallMethod(
            kind=InstallKind.MCP_STDIO, command="npx", args=["-y", "curated@1.0.0"],
        ),
    )
    before = declared.model_dump()

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a registry-declared component must not trigger an npm lookup")

    asyncio.run(pin_npm_install(
        declared, repository_full_name="owner/repo",
        client=httpx.AsyncClient(transport=httpx.MockTransport(explode)),
    ))
    assert declared.model_dump() == before


def test_an_http_mcp_server_is_warned_but_not_refused() -> None:
    """An HTTP MCP server is an endpoint, not code this program fetches, so it has no version.

    Refusing it for lacking a pin it cannot have would drop the official GitHub MCP server,
    whose README is where its URL legitimately comes from.
    """
    component = ComponentValidator().validate(
        normalize_candidate(raw("Point your Agent at https://api.example.com/mcp/"))
    )
    assert component.install_method.kind == InstallKind.MCP_HTTP
    assert component.install_method.from_readme
    assert component.recommendable
    assert any(f.rule == "install.readme_derived" for f in analyze_security([component]))


# --- the approval screen -------------------------------------------------------------------

def test_the_risk_review_says_the_command_came_from_a_README() -> None:
    """The finding that was missing entirely: findings was empty for exactly this case."""
    client = registry({"name": "sast-mcp", "version": "1.4.2",
                       "repository": "github:someone/mcp-server"})
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    rules = {finding.rule: finding for finding in analyze_security([component])}
    assert rules["install.readme_derived"].level.value == "WARNING"
    assert "README" in rules["install.readme_derived"].message
    assert "sast-mcp@1.4.2" in rules["install.version_pinned"].message


# --- the token must not follow the request ------------------------------------------------

def test_the_github_token_does_not_reach_the_npm_registry(monkeypatch) -> None:
    """The defect this fix could have introduced, had it reused the GitHub client.

    That client carries `Authorization: Bearer <GITHUB_TOKEN>`. Sending a user's token to a
    third party because two requests sit in the same function would be worse than the problem
    being fixed, so the request the resolver builds is inspected directly.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_sentinel_value")
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"name": "sast-mcp", "version": "1.0.0",
                                         "repository": "someone/mcp-server"})

    component = normalize_candidate(raw("npx -y sast-mcp"))
    asyncio.run(pin_npm_install(
        component, repository_full_name="someone/mcp-server",
        client=httpx.AsyncClient(transport=httpx.MockTransport(record)),
    ))

    assert seen, "the resolver made no request"
    for request in seen:
        assert "registry.npmjs.org" in str(request.url)
        assert "authorization" not in {key.lower() for key in request.headers}
        assert not any("sentinel" in value.lower() for value in request.headers.values())


def test_the_resolver_asks_for_the_latest_dist_tag_not_the_whole_document() -> None:
    """A popular package's full document is megabytes of version history."""
    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"name": "x", "version": "1.0.0"})

    asyncio.run(resolve_package(
        "x", client=httpx.AsyncClient(transport=httpx.MockTransport(record)),
    ))
    assert seen == ["https://registry.npmjs.org/x/latest"]


# --- the wiring ----------------------------------------------------------------------------

MCP_REPOSITORY = "someone/sast-mcp"


def mcp_github_handler(request: httpx.Request) -> httpx.Response:
    """A GitHub that returns one MCP server whose install line lives in its README."""
    path = request.url.path
    headers = {"x-ratelimit-remaining": "42"}
    if path == "/rate_limit":
        return httpx.Response(200, headers=headers, json={
            "resources": {"search": {"remaining": 42}, "core": {"remaining": 42}},
        })
    if path == "/search/repositories":
        return httpx.Response(200, headers=headers, json={"items": [{
            "full_name": MCP_REPOSITORY,
            "html_url": f"https://github.com/{MCP_REPOSITORY}",
            "private": False, "pushed_at": "2026-09-20T00:00:00Z",
        }]})
    if path == f"/repos/{MCP_REPOSITORY}":
        return httpx.Response(200, headers=headers, json={
            "name": "sast-mcp", "full_name": MCP_REPOSITORY,
            "html_url": f"https://github.com/{MCP_REPOSITORY}",
            "description": "MCP server for source code analysis and vulnerability research",
            "default_branch": "main", "pushed_at": "2026-09-20T00:00:00Z",
            "stargazers_count": 12, "forks_count": 1, "archived": False,
            "license": {"spdx_id": "MIT"},
        })
    if path.endswith("/readme"):
        return httpx.Response(200, headers=headers, text=(
            "MCP server for source code analysis and vulnerability research.\n"
            "## Install\n```\nnpx -y sast-mcp\n```\n"
        ))
    if path.endswith("/commits/main"):
        return httpx.Response(200, headers=headers, json={"sha": "deadbeef"})
    if path.endswith("/releases/latest"):
        return httpx.Response(404, headers=headers, json={"message": "not found"})
    if path.endswith("/git/trees/main"):
        return httpx.Response(200, headers=headers, json={
            "tree": [{"path": "mcp.json", "type": "blob"}],
        })
    if path.endswith("/contents/mcp.json"):
        return httpx.Response(200, headers=headers, text='{"name": "sast-mcp"}')
    raise AssertionError(f"unexpected request: {request.url}")


def run_discovery(npm_handler) -> object:
    from agent_guidance.sources.cache import CandidateCache
    from agent_guidance.sources.github import GitHubSource

    github = httpx.AsyncClient(
        transport=httpx.MockTransport(mcp_github_handler), base_url="https://api.github.com",
    )
    npm = httpx.AsyncClient(transport=httpx.MockTransport(npm_handler))
    source = GitHubSource(
        validator=ComponentValidator(), cache=CandidateCache(path=None),
        client=github, npm_client=npm,
    )
    try:
        return asyncio.run(source.discover(["mcp security server"]))
    finally:
        asyncio.run(github.aclose())
        asyncio.run(npm.aclose())


def test_discovery_pins_an_npm_mcp_server_end_to_end() -> None:
    """The unit tests prove the resolver works; this proves discovery actually calls it."""
    asked: list[str] = []

    def npm(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json={
            "name": "sast-mcp", "version": "2.1.0",
            "repository": f"https://github.com/{MCP_REPOSITORY}",
        })

    result = run_discovery(npm)

    assert asked == ["https://registry.npmjs.org/sast-mcp/latest"]
    candidate = result.candidates[0]
    assert candidate.install_method.args == ["-y", "sast-mcp@2.1.0"]
    assert candidate.recommendable and result.validated == 1


def test_discovery_drops_an_npm_mcp_server_it_cannot_pin() -> None:
    """Discovered, counted, and not offered — with the reason recorded on the candidate."""
    def npm(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not found"})

    result = run_discovery(npm)

    assert result.discovered == 1 and result.validated == 0
    candidate = result.candidates[0]
    assert not candidate.recommendable
    assert "no package named sast-mcp" in " ".join(candidate.validation_warnings)


def test_a_skill_on_a_branch_is_warned_not_refused() -> None:
    """The same gap in the other install kind, answered differently and on purpose.

    `_install_ref` falls back to the default branch when the commit lookup did not land, which
    happens under an anonymous rate limit. Refusing there would shrink the candidate set for a
    reason that has nothing to do with the repository, so this warns: the approval screen says
    the install follows a branch, and the user decides.
    """
    component = ComponentValidator().validate(normalize_candidate(RawCandidate(
        source="github", source_type="github", repository_full_name="owner/sec-skill",
        repository_url="https://github.com/owner/sec-skill",
        readme="Codex source code analysis and vulnerability research skill",
        metadata={"description": "security skill", "default_branch": "main"},
        files={"skills/audit/SKILL.md": "---\nname: s\ndescription: d\n---\n"},
        tree_paths=["skills/audit/SKILL.md"],
    )))

    assert component.install_method.ref == "main"
    assert component.recommendable
    assert any("not pinned to a commit" in w for w in component.validation_warnings)
    # And it reaches the approval screen, which is the whole point of warning rather than
    # recording it somewhere only the author reads.
    assert any(
        "not pinned to a commit" in finding.message for finding in analyze_security([component])
    )


def test_the_resolver_opens_its_own_client_when_given_none(monkeypatch) -> None:
    """The production path. Discovery passes no client, so this is what actually runs.

    Covering only the injected-client path would leave the real one — which has to build a
    credential-free client and close it — exercised for the first time on a user's machine.
    """
    import agent_guidance.sources.npm as npm

    built: list[dict] = []
    closed: list[bool] = []

    def record_client(**kwargs):
        built.append(kwargs)
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "name": "sast-mcp", "version": "3.0.0", "repository": "someone/mcp-server",
            })
        ))
        original = client.aclose

        async def closing():
            closed.append(True)
            await original()

        client.aclose = closing
        return client

    monkeypatch.setattr(npm, "create_async_client", record_client)
    component = normalize_candidate(raw("npx -y sast-mcp"))
    asyncio.run(npm.pin_npm_install(component, repository_full_name="someone/mcp-server"))

    assert built, "no client was built"
    assert "headers" not in built[0], "the resolver must not add headers of its own"
    assert closed == [True], "the client it opened was not closed"
    assert component.install_method.args == ["-y", "sast-mcp@3.0.0"]


def test_a_registry_answer_without_a_version_is_refused() -> None:
    """A 200 is not a resolution. Trusting the status alone would pin to `None`."""
    client = registry({"name": "sast-mcp"})
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert not component.recommendable
    assert "no version for sast-mcp" in " ".join(component.validation_warnings)


def test_a_registry_that_times_out_is_refused() -> None:
    """Separated from a connection error because the message a user reads differs."""
    def stall(request: httpx.Request) -> httpx.Response:
        raise asyncio.TimeoutError()

    client = httpx.AsyncClient(transport=httpx.MockTransport(stall))
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert not component.recommendable
    assert "timed out" in " ".join(component.validation_warnings)


def test_a_registry_error_status_is_refused() -> None:
    """A 500 is neither "no such package" nor a resolution."""
    client = registry({"error": "upstream"}, status=500)
    component = pin(normalize_candidate(raw("npx -y sast-mcp")), "someone/mcp-server", client)

    assert not component.recommendable
    assert "could not be reached" in " ".join(component.validation_warnings)
