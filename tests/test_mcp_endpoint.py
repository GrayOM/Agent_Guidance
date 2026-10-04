"""Which URL a discovered HTTP MCP server is registered against.

This is a report from a real run. The GitHub MCP Server was installed and written into both
Agent configs as:

    [mcp_servers.github]
    url = "https://insiders.vscode.dev/redirect/mcp/"
    bearer_token_env_var = "GITHUB_PAT_TOKEN"

That host is Microsoft's editor-install redirect, not an MCP endpoint. Two defects met to
produce it, and each has a test here.

  - The pattern that reads an endpoint out of a README matched a *prefix* of a longer URL, so
    the two "Install in VS Code" badges at the top of that README — pointing at
    `.../redirect/mcp/install?name=...` — read as endpoints. `urls[0]` took the first.
  - The built-in registry declares the endpoint correctly. The merge preferred the scraped
    URL because the official source outranks the registry, and kept the registry's
    `bearer_token_env_var`. The result configured the user's GitHub PAT to be sent to a host
    nobody chose.

Nothing was exfiltrated, because of whose host it happens to be. The shape is a credential
going somewhere unintended, which is not a shape to leave in place.

The README is a fixture captured from the repository rather than a hand-written sample: the
ordering is the defect, and a sample written from memory would have put the endpoint first
and passed.
"""

from pathlib import Path

import pytest

from agent_guidance.core.discovery import _merge_candidates
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod, SourceType,
    TrustMetadata,
)
from agent_guidance.sources.normalizer import _mcp_endpoint


FIXTURE = Path(__file__).parent / "fixtures" / "github_mcp_server_readme.md"
REAL_ENDPOINT = "https://api.githubcopilot.com/mcp/"
THE_BADGE = "https://insiders.vscode.dev/redirect/mcp/"


def test_the_real_github_mcp_readme_resolves_to_its_endpoint() -> None:
    """The exact case that shipped wrong."""
    readme = FIXTURE.read_text(encoding="utf-8")
    assert THE_BADGE in readme, "the fixture no longer contains the badge this test is about"

    assert _mcp_endpoint(readme) == REAL_ENDPOINT


@pytest.mark.parametrize(("readme", "expected"), [
    # A `/mcp/` in the middle of a path is not an endpoint at that path.
    ("Install: https://insiders.vscode.dev/redirect/mcp/install?name=x", None),
    ("See https://code.visualstudio.com/docs/copilot/chat/mcp for help", None),
    # A badge host is not an endpoint even when the URL does end at /mcp.
    ("Install from https://aka.ms/vs/mcp", None),
    # A plain endpoint still works, with and without the trailing slash.
    ("Connect to https://example.test/mcp/", "https://example.test/mcp/"),
    ("Connect to https://example.test/mcp", "https://example.test/mcp"),
    # Markdown delimiters end a URL, and sentence punctuation is not part of it.
    ("[docs](https://example.test/mcp/)", "https://example.test/mcp/"),
    ("Use `https://example.test/mcp/` today", "https://example.test/mcp/"),
    ("The endpoint is https://example.test/mcp.", "https://example.test/mcp"),
])
def test_what_counts_as_an_endpoint(readme, expected) -> None:
    assert _mcp_endpoint(readme) == expected


def test_the_most_repeated_url_wins() -> None:
    """A README repeats its endpoint through its examples and mentions an aside once.

    Order alone is not enough: an enterprise or self-hosted example can legitimately appear
    before the hosted endpoint.
    """
    readme = (
        "Self-hosted users: https://copilot.internal.test/mcp\n"
        "Endpoint: https://api.example.test/mcp/\n"
        "Example: https://api.example.test/mcp/\n"
        "Also: https://api.example.test/mcp/\n"
    )
    assert _mcp_endpoint(readme) == "https://api.example.test/mcp/"


def _component(*, source: SourceType, url: str, from_readme: bool, bearer: str | None) -> Component:
    return Component(
        id="github", name="GitHub MCP Server", type=ComponentType.MCP,
        github_url="https://github.com/github/github-mcp-server",
        source=source.value,
        capabilities={Capability.CODE_REVIEW},
        supported_agents={AgentType.CODEX, AgentType.CLAUDE_CODE},
        trust=TrustMetadata(source_type=source, official=source is SourceType.OFFICIAL),
        install_method=InstallMethod(
            kind=InstallKind.MCP_HTTP, url=url, from_readme=from_readme,
            bearer_token_env_var=bearer,
        ),
    )


def test_a_declared_endpoint_survives_a_merge_with_a_scraped_one() -> None:
    """The second half of the defect, and the one that would have caught it alone.

    The registry declares the endpoint; the official source reads the same repository's README
    and guesses. Ranking put official first, so the guess replaced the fact and inherited the
    registry's bearer token — a credential pointed at a host nobody chose.
    """
    scraped = _component(source=SourceType.OFFICIAL, url=THE_BADGE, from_readme=True, bearer=None)
    declared = _component(
        source=SourceType.REGISTRY, url=REAL_ENDPOINT, from_readme=False,
        bearer="GITHUB_PAT_TOKEN",
    )

    merged = _merge_candidates([scraped, declared])

    assert len(merged) == 1
    method = merged[0].install_method
    assert str(method.url) == REAL_ENDPOINT, "a scraped URL replaced a declared one"
    assert method.bearer_token_env_var == "GITHUB_PAT_TOKEN"
    assert not method.from_readme


def test_the_order_sources_are_merged_in_does_not_change_the_endpoint() -> None:
    """The rule has to hold whichever side the merge keeps as its base."""
    scraped = _component(source=SourceType.OFFICIAL, url=THE_BADGE, from_readme=True, bearer=None)
    declared = _component(
        source=SourceType.REGISTRY, url=REAL_ENDPOINT, from_readme=False,
        bearer="GITHUB_PAT_TOKEN",
    )

    for pair in ([scraped, declared], [declared, scraped]):
        merged = _merge_candidates(pair)
        assert str(merged[0].install_method.url) == REAL_ENDPOINT


def test_a_scraped_endpoint_is_still_used_when_nothing_declares_one() -> None:
    """Only a declared method displaces a scraped one; a scraped one is better than none.

    Without this the fix would silently drop every HTTP MCP server the registry has never
    heard of, which is most of what discovery is for.
    """
    scraped = _component(
        source=SourceType.GITHUB, url="https://someone.test/mcp/", from_readme=True, bearer=None,
    )

    merged = _merge_candidates([scraped])

    assert str(merged[0].install_method.url) == "https://someone.test/mcp/"
    assert merged[0].install_method.from_readme


@pytest.mark.parametrize(("readme", "expected"), [
    # A dot inside a path is not the end of the URL, so this is a file and not an endpoint.
    ("Schema at https://example.test/mcp.json", None),
    ("See https://example.test/mcp.html for the spec", None),
])
def test_a_dot_in_a_path_is_not_a_sentence_ending(readme, expected) -> None:
    """The cost of treating a full stop as a boundary, bounded.

    `/mcp.` at the end of a sentence is an endpoint; `/mcp.json` is a file. Accepting the
    first without accepting the second is why the lookahead requires whitespace or end of
    line after the dot.
    """
    assert _mcp_endpoint(readme) == expected
