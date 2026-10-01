"""A question the interview can ask must lead to a component that can be found.

Three tables have to agree, and nothing used to hold them together:

- `TASKS` / `DOMAIN_CAPABILITIES` / `TASK_CAPABILITIES` turn answers into capabilities
- `CAPABILITY_TERMS` turns a capability into a GitHub search
- `CAPABILITY_KEYWORDS` recognises that capability in a repository GrayOM found

A capability missing from either of the last two is unsatisfiable: it is asked about, and
then no candidate can ever cover it. `planning`, `development_workflow` and `test_execution`
were in exactly that state, and `report_support` was in the enum while no question produced
it. These tests make the tables fail loudly instead of quietly recommending nothing.
"""

import pytest

from grayom_agent_guidance.cli.interview import TASKS, build_answer
from grayom_agent_guidance.core.capability_inference import (
    DOMAIN_CAPABILITIES, TASK_CAPABILITIES, infer_capabilities, infer_task_capabilities,
)
from grayom_agent_guidance.core.query_builder import CAPABILITY_TERMS, build_queries
from grayom_agent_guidance.models import AgentType, Capability, ComponentType, SetupMode, WorkDomain
from grayom_agent_guidance.sources.normalizer import CAPABILITY_KEYWORDS, _mentions


def _asked_capabilities() -> set[Capability]:
    asked: set[Capability] = set()
    for capabilities in DOMAIN_CAPABILITIES.values():
        asked |= capabilities
    for capabilities in TASK_CAPABILITIES.values():
        asked |= capabilities
    return asked


# --- the three tables agree ----------------------------------------------------------


def test_every_capability_can_be_searched_for() -> None:
    missing = sorted(item.value for item in set(Capability) - set(CAPABILITY_TERMS))

    assert not missing, f"no GitHub search term, so these can never be covered: {missing}"


def test_every_capability_can_be_recognised_in_a_repository() -> None:
    missing = sorted(item.value for item in set(Capability) - set(CAPABILITY_KEYWORDS))

    assert not missing, (
        f"no README keywords, so a discovered repository can never carry these: {missing}"
    )


def test_no_capability_exists_that_nothing_asks_for() -> None:
    unreachable = sorted(item.value for item in set(Capability) - _asked_capabilities())

    assert not unreachable, f"in the enum but no question produces them: {unreachable}"


# --- the interview is detailed everywhere --------------------------------------------


def test_every_work_domain_asks_detailed_questions() -> None:
    """A domain with no tasks asks one broad question and recommends just as broadly."""
    empty = sorted(domain.value for domain in WorkDomain if not TASKS.get(domain))

    assert not empty, f"these domains have no detailed tasks: {empty}"


def test_every_offered_task_maps_to_capabilities() -> None:
    offered = {task for tasks in TASKS.values() for task in tasks}
    unmapped = sorted(offered - set(TASK_CAPABILITIES))

    assert not unmapped, f"selectable but contributes nothing: {unmapped}"


def test_every_task_mapping_is_reachable_from_some_domain() -> None:
    offered = {task for tasks in TASKS.values() for task in tasks}
    orphaned = sorted(set(TASK_CAPABILITIES) - offered)

    assert not orphaned, f"mapped but no domain offers them: {orphaned}"


@pytest.mark.parametrize("domain", list(WorkDomain))
def test_each_domain_produces_a_recognisable_profile(domain: WorkDomain) -> None:
    """Selecting a domain and all its tasks must say something specific to that domain."""
    answer = build_answer(
        [AgentType.CLAUDE_CODE], [domain], list(TASKS[domain]), SetupMode.MINIMAL,
    )
    capabilities = infer_capabilities(answer)

    assert capabilities
    assert capabilities <= set(CAPABILITY_TERMS)
    queries = build_queries([AgentType.CLAUDE_CODE], capabilities, ComponentType.MCP, limit=5)
    assert queries


def test_devops_and_mobile_no_longer_ask_for_the_same_thing() -> None:
    """Both domains used to infer an identical capability set, so both got the same Plan."""
    profiles = {
        domain: infer_capabilities(build_answer(
            [AgentType.CLAUDE_CODE], [domain], list(TASKS[domain]), SetupMode.MINIMAL,
        ))
        for domain in WorkDomain
    }

    assert profiles[WorkDomain.DEVOPS] != profiles[WorkDomain.MOBILE_DEVELOPMENT]
    assert DOMAIN_CAPABILITIES[WorkDomain.DEVOPS] != DOMAIN_CAPABILITIES[WorkDomain.MOBILE_DEVELOPMENT]
    assert len({frozenset(value) for value in profiles.values()}) == len(WorkDomain), (
        "two domains still produce the same profile"
    )


def test_a_devops_profile_searches_for_devops_tools() -> None:
    answer = build_answer(
        [AgentType.CLAUDE_CODE], [WorkDomain.DEVOPS],
        ["kubernetes_operations", "infrastructure_as_code"], SetupMode.MINIMAL,
    )
    queries = build_queries(
        [AgentType.CLAUDE_CODE], infer_capabilities(answer), ComponentType.MCP, limit=5,
    )

    assert any("kubernetes" in query for query in queries)
    assert any("terraform" in query for query in queries)


def test_an_explicitly_selected_task_outranks_the_domain_base() -> None:
    """A mobile developer who picked iOS had it cut by the CI/CD the domain implies."""
    answer = build_answer(
        [AgentType.CLAUDE_CODE], [WorkDomain.MOBILE_DEVELOPMENT],
        ["ios_app", "cross_platform_app"], SetupMode.MINIMAL,
    )
    capabilities = infer_capabilities(answer)
    selected = infer_task_capabilities(answer)

    assert Capability.CI_CD in capabilities and Capability.CI_CD not in selected
    narrow = build_queries(
        [AgentType.CLAUDE_CODE], capabilities, ComponentType.MCP, limit=3, preferred=selected,
    )

    assert any("iOS" in query for query in narrow)
    assert any("React Native Flutter" in query for query in narrow)
    assert not any("CI/CD" in query for query in narrow)


def test_task_capabilities_are_a_subset_of_the_whole_profile() -> None:
    for domain in WorkDomain:
        answer = build_answer(
            [AgentType.CLAUDE_CODE], [domain], list(TASKS[domain]), SetupMode.MINIMAL,
        )
        assert infer_task_capabilities(answer) <= infer_capabilities(answer), domain.value


# --- repository recognition ----------------------------------------------------------


def test_a_keyword_matches_a_word_start_and_its_grown_suffix() -> None:
    assert _mentions("audits the code", ("audit",))
    assert _mentions("auditing tool", ("audit",))
    assert _mentions("terraform modules", ("terraform",))


def test_an_ies_plural_is_listed_because_the_anchor_cannot_reach_it() -> None:
    """-y to -ies is a spelling change, so prefix anchoring never covered it."""
    assert not _mentions("fixes vulnerabilities", ("vulnerability",))

    for text, capability in (
        ("fixes vulnerabilities", Capability.VULNERABILITY_RESEARCH),
        ("updates dependencies", Capability.DEPENDENCY_MANAGEMENT),
        ("scans repositories", Capability.REPOSITORY_ACCESS),
    ):
        assert _mentions(text, CAPABILITY_KEYWORDS[capability]), text


def test_a_short_keyword_does_not_match_inside_an_unrelated_word() -> None:
    """A plain substring test tagged every repository mentioning "studios" as iOS."""
    assert not _mentions("built by acme studios for radios", ("ios",))
    assert _mentions("an ios app helper", ("ios",))
    assert not _mentions("various scenarios", ("ios",))
