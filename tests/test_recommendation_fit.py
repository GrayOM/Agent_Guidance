"""Which candidate a sprawling README beats, and which component types substitute.

Both of these come from one real run. A user asked for web development and AI-Agent
development and was shown this order, measured from the repositories themselves:

    component                  claims  covers  precision  README
    samugit83-redamon              25       7       0.28  101,752 chars  <- 1st
    aquaticat-monochromatic        14       5       0.36   13,287 chars  <- 2nd
    superpowers                     5       4       0.80                <- 3rd
    github (official)               3       2       0.67                <- 4th

First place went to an autonomous exploitation framework whose README claims 25 of the 37
capabilities that exist, and which installed 1 of its 15 Skills because that was all that
matched the work. Second went to a 148-package monorepo. `coverage` was the first sort key
and it counts claims, so the ranking read as "the longer the README, the higher the rank".

Fixing the order then exposed a second defect underneath it. The coverage bookkeeping was
keyed by Agent and capability with no component type, so a Skill that mentions code review
made the official GitHub MCP server redundant. It had survived only by being ordered first.
"""

import pytest

from agent_guidance.cli.interview import build_answer
from agent_guidance.core.capability_inference import infer_capabilities
from agent_guidance.core.recommender import _fit, _priority_key, recommend
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod,
    MaintenanceMetadata, MaintenanceStatus, SetupMode, SourceType, TrustMetadata, WorkDomain,
)


NEEDED = {
    Capability.AGENT_DEVELOPMENT, Capability.CODE_EDITING, Capability.CODE_REVIEW,
    Capability.DEVELOPMENT_WORKFLOW, Capability.NETWORK_ACCESS, Capability.REPORTING,
    Capability.REPOSITORY_ACCESS, Capability.SECURITY_ANALYSIS, Capability.TESTING,
}

# Sorted, so a slice of it is the same set on every run. An unsorted set slice made one of
# these tests pass or fail depending on hash order, which is worse than no test.
WANTED = sorted(NEEDED, key=lambda capability: capability.value)

# Everything the inference can produce, so a candidate can be given a claim as broad as the
# one that won. Padding is drawn from here rather than invented.
SPARE = sorted(
    (capability for capability in Capability if capability not in NEEDED),
    key=lambda capability: capability.value,
)


def candidate(
    identifier: str,
    *,
    covers: set[Capability],
    claims: int,
    kind: ComponentType = ComponentType.SKILL,
    official: bool = False,
) -> Component:
    """A component claiming `claims` capabilities, of which `covers` are wanted."""
    padding = set(SPARE[: max(0, claims - len(covers))])
    install = (
        InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp/")
        if kind == ComponentType.MCP
        else InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/o/r", ref="a" * 40,
        )
    )
    return Component(
        id=identifier, name=identifier, type=kind,
        github_url=f"https://github.com/owner/{identifier}",
        capabilities=covers | padding,
        supported_agents={AgentType.CODEX, AgentType.CLAUDE_CODE},
        install_method=install,
        official=official,
        trust=TrustMetadata(
            source_type=SourceType.OFFICIAL if official else SourceType.GITHUB,
            official=official, verified=True,
        ),
        maintenance_metadata=MaintenanceMetadata(status=MaintenanceStatus.ACTIVE, license="MIT"),
        recommendable=True,
    )


# The four candidates of the real run, at their measured claim and coverage counts.
REDAMON = candidate("samugit83-redamon", covers=set(WANTED[:7]), claims=25)
MONOCHROMATIC = candidate("aquaticat-monochromatic", covers=set(WANTED[:5]), claims=14)
SUPERPOWERS = candidate("superpowers", covers=set(WANTED[:4]), claims=5)
GITHUB_MCP = candidate(
    "github", covers={Capability.CODE_REVIEW, Capability.REPOSITORY_ACCESS}, claims=3,
    kind=ComponentType.MCP, official=True,
)


def test_the_measured_precision_is_what_the_repositories_actually_showed() -> None:
    """Guards the numbers the rest of this file reasons about."""
    assert len(REDAMON.capabilities) == 25
    assert len(REDAMON.capabilities & NEEDED) == 7
    assert len(SUPERPOWERS.capabilities) == 5
    assert len(SUPERPOWERS.capabilities & NEEDED) == 4


@pytest.mark.parametrize("mode", [SetupMode.MINIMAL, SetupMode.PERFORMANCE])
def test_a_focused_candidate_outranks_a_sprawling_one(mode) -> None:
    """The inversion, in both modes: the fix must not hold in one and not the other."""
    order = sorted(
        [REDAMON, MONOCHROMATIC, SUPERPOWERS],
        key=lambda item: _priority_key(item, NEEDED, mode),
    )
    assert [item.id for item in order][0] == "superpowers", (
        "a README claiming 25 capabilities still outranks one claiming 5"
    )


def test_coverage_still_decides_between_equally_focused_candidates() -> None:
    """Precision replaces coverage as the first key; it does not replace coverage.

    Two candidates equally on-target are separated by how much of the work they cover, or the
    fix would prefer a one-capability component to one that does the whole job.
    """
    narrow = candidate("narrow", covers=set(WANTED[:2]), claims=2)
    broad = candidate("broad", covers=set(WANTED[:6]), claims=6)

    order = sorted(
        [narrow, broad], key=lambda item: _priority_key(item, NEEDED, SetupMode.MINIMAL),
    )
    assert [item.id for item in order] == ["broad", "narrow"]


def test_a_candidate_covering_nothing_scores_zero() -> None:
    assert _fit(candidate("unrelated", covers=set(), claims=9), NEEDED) == 0.0


def test_a_sprawling_candidate_is_still_selected_when_it_is_the_only_cover() -> None:
    """Focus changes the order, not what is possible.

    The point is that sprawl does not win on arithmetic — not that a broad project is
    unusable. When nothing focused covers a capability, the broad candidate is still the
    answer, and in the real run `redamon` was still selected second for exactly that reason.
    """
    answer = build_answer(
        agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        domains=[WorkDomain.WEB_DEVELOPMENT, WorkDomain.AI_AGENT_DEVELOPMENT],
        tasks=["frontend", "backend", "coding_agent", "security_agent"],
        mode=SetupMode.MINIMAL,
    )
    inferred = sorted(infer_capabilities(answer), key=lambda item: item.value)
    sprawling = candidate("sprawling", covers=set(inferred), claims=25)
    focused = candidate("focused", covers=set(inferred[:2]), claims=2)

    plan = recommend(answer, [sprawling, focused])
    chosen = [component.id for component in plan.selected]

    assert chosen[0] == "focused", "the focused candidate should be preferred first"
    assert "sprawling" in chosen, "the broad candidate still fills what is left"


def test_a_skill_does_not_make_an_mcp_server_redundant() -> None:
    """The defect the reordering exposed.

    A Skill is written instructions the Agent reads; an MCP server is tools it can call. Both
    carry `code_review`. With the coverage key blind to component type, selecting a Skill that
    mentions code review dropped the official GitHub MCP server as "adds no capability beyond
    selected components" — and it had only ever survived by being ordered first.
    """
    answer = build_answer(
        agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        domains=[WorkDomain.WEB_DEVELOPMENT, WorkDomain.AI_AGENT_DEVELOPMENT],
        tasks=["frontend", "backend", "coding_agent", "security_agent"],
        mode=SetupMode.MINIMAL,
    )
    inferred = infer_capabilities(answer)
    skill = candidate("a-skill", covers=inferred & NEEDED, claims=len(inferred & NEEDED))
    mcp = candidate(
        "github", covers={Capability.CODE_REVIEW, Capability.REPOSITORY_ACCESS}, claims=3,
        kind=ComponentType.MCP, official=True,
    )

    plan = recommend(answer, [skill, mcp])
    chosen = [component.id for component in plan.selected]

    assert "a-skill" in chosen
    assert "github" in chosen, "a Skill covering code_review displaced the official MCP server"


def test_two_skills_covering_the_same_capability_still_deduplicate() -> None:
    """Adding the type must not stop deduplication within a type.

    If it did, every Skill claiming an already-covered capability would be installed, which is
    the opposite problem: the Agent's context spent on work the user did not ask for.
    """
    answer = build_answer(
        agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        domains=[WorkDomain.WEB_DEVELOPMENT],
        tasks=["frontend", "backend"],
        mode=SetupMode.MINIMAL,
    )
    capabilities = infer_capabilities(answer)
    same = capabilities & NEEDED or {Capability.CODE_EDITING}
    first = candidate("first-skill", covers=same, claims=len(same))
    second = candidate("second-skill", covers=same, claims=len(same))

    plan = recommend(answer, [first, second])

    assert len(plan.selected) == 1, [item.id for item in plan.selected]
