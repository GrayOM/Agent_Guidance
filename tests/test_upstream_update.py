"""`grayom update` has to compare against what upstream publishes now.

Comparing against the Local Registry's pinned refs meant a component was only ever out of
date when GrayOM itself shipped a new Registry, and a component discovered on GitHub was
never comparable at all.
"""

import asyncio

import httpx

from grayom_agent_guidance.core.update import build_update_plan
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod, Ownership,
)
from grayom_agent_guidance.sources.base import RawCandidate
from grayom_agent_guidance.sources.normalizer import _install_ref
from grayom_agent_guidance.sources.upstream import (
    UpstreamRef, UpstreamResolver, parse_repository, pinning_of, resolve_upstream_refs,
)
from grayom_agent_guidance.state import ManagedComponent, StateStore

HEAD = "a" * 40
INSTALLED = "b" * 40
REPOSITORY = "https://github.com/someone/skills"


def _state(tmp_path, **overrides) -> StateStore:
    values = {
        "component_id": "someone-skills", "agents": [AgentType.CLAUDE_CODE],
        "ownership": Ownership.GRAYOM_INSTALLED, "transaction_id": "t",
        "component_name": "Someone's Skills", "component_type": ComponentType.SKILL,
        "source_repository": REPOSITORY, "source_ref": INSTALLED,
        "install_method": InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository=REPOSITORY, ref=INSTALLED,
        ),
    }
    values.update(overrides)
    managed = ManagedComponent(**values)
    store = StateStore(tmp_path / "state" / "components.json")
    store.document.components[managed.component_id] = managed
    return store


def _registry_component(ref: str) -> Component:
    return Component(
        id="someone-skills", name="Someone's Skills", type=ComponentType.SKILL,
        github_url=REPOSITORY, source="local_registry", capabilities={Capability.TESTING},
        supported_agents={AgentType.CLAUDE_CODE},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository=REPOSITORY, ref=ref,
        ),
    )


# --- reference parsing ---------------------------------------------------------------


def test_pinning_is_read_from_the_shape_of_the_installed_reference() -> None:
    assert pinning_of(HEAD) == "commit"
    assert pinning_of("v1.2.3") == "release"
    assert pinning_of(None) is None


def test_only_github_https_repositories_are_resolvable() -> None:
    assert parse_repository(REPOSITORY) == ("someone", "skills")
    assert parse_repository("https://github.com/someone/skills.git") == ("someone", "skills")
    assert parse_repository("https://gitlab.com/someone/skills") is None
    assert parse_repository("git@github.com:someone/skills.git") is None
    assert parse_repository(None) is None


def test_a_pushed_at_timestamp_is_never_used_as_an_install_reference() -> None:
    """source_version is a cache key; git cannot resolve `fetch origin 2026-01-01T00:00:00Z`."""
    raw = RawCandidate(
        repository_full_name="someone/skills", repository_url=REPOSITORY,
        source_type="github", source_version="2026-01-01T00:00:00Z",
        metadata={"default_branch": "main"},
    )

    assert _install_ref(raw) == "main"
    assert _install_ref(raw.model_copy(update={"metadata": {"head_sha": HEAD}})) == HEAD


# --- resolving upstream --------------------------------------------------------------


def _resolve(handler, store_values=None) -> dict[str, UpstreamRef]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    managed = ManagedComponent(**{
        "component_id": "someone-skills", "agents": [AgentType.CLAUDE_CODE],
        "ownership": Ownership.GRAYOM_INSTALLED, "transaction_id": "t",
        "source_repository": REPOSITORY, "source_ref": INSTALLED,
        **(store_values or {}),
    })
    result = asyncio.run(UpstreamResolver(client=client).resolve([managed]))
    asyncio.run(client.aclose())
    return result


def test_a_commit_pinned_component_is_compared_with_the_head_commit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/someone/skills/commits"
        return httpx.Response(200, json=[{"sha": HEAD}])

    reference = _resolve(handler)["someone-skills"]

    assert reference.checked and reference.changed
    assert reference.pinning == "commit"
    assert reference.latest_ref == HEAD
    assert reference.describe() == "upstream commit changed"


def test_a_tag_pinned_component_is_compared_with_the_latest_release() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/someone/skills/releases/latest"
        return httpx.Response(200, json={"tag_name": "v2.0.0"})

    reference = _resolve(handler, {"source_ref": "v1.0.0"})["someone-skills"]

    assert reference.checked and reference.changed
    assert reference.pinning == "release"
    assert reference.latest_ref == "v2.0.0"


def test_an_unchanged_upstream_is_reported_as_checked_and_unchanged() -> None:
    reference = _resolve(lambda request: httpx.Response(200, json=[{"sha": INSTALLED}]))

    assert reference["someone-skills"].checked
    assert not reference["someone-skills"].changed


def test_a_tag_pinned_component_without_releases_is_unchecked_not_unchanged() -> None:
    reference = _resolve(
        lambda request: httpx.Response(404, json={"message": "Not Found"}),
        {"source_ref": "v1.0.0"},
    )["someone-skills"]

    assert not reference.checked
    assert "no release" in (reference.reason or "")


def test_an_upstream_error_is_reported_rather_than_claiming_up_to_date() -> None:
    reference = _resolve(
        lambda request: httpx.Response(500, json={"message": "server error"})
    )["someone-skills"]

    assert not reference.checked and not reference.changed
    assert reference.reason is not None


def test_a_non_github_upstream_is_not_requested_at_all() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no request expected, got {request.url}")

    reference = _resolve(handler, {"source_repository": "https://example.test/skills"})

    assert not reference["someone-skills"].checked


def test_a_transport_failure_degrades_to_an_empty_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com",
    )
    managed = ManagedComponent(
        component_id="someone-skills", agents=[AgentType.CLAUDE_CODE],
        ownership=Ownership.GRAYOM_INSTALLED, transaction_id="t",
        source_repository=REPOSITORY, source_ref=INSTALLED,
    )
    result = resolve_upstream_refs([managed], client=client)
    asyncio.run(client.aclose())

    assert not result["someone-skills"].checked


# --- planning the update -------------------------------------------------------------


def test_upstream_drives_the_update_for_a_component_absent_from_the_registry(tmp_path) -> None:
    store = _state(tmp_path)
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, latest_ref=HEAD,
        pinning="commit", checked=True,
    )}

    plan = build_update_plan(store, [], upstream=upstream)

    assert [item.component.id for item in plan.items] == ["someone-skills"]
    item = plan.items[0]
    assert item.current_ref == INSTALLED
    assert item.target_ref == HEAD
    assert item.component.install_method.ref == HEAD, "the transaction must install the new ref"
    assert item.agents == [AgentType.CLAUDE_CODE]


def test_a_checked_and_unchanged_upstream_stops_a_stale_registry_from_proposing(tmp_path) -> None:
    """Upstream is authoritative when it could be read, so an older Registry cannot override it."""
    store = _state(tmp_path)
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, latest_ref=INSTALLED,
        pinning="commit", checked=True,
    )}

    plan = build_update_plan(store, [_registry_component("c" * 40)], upstream=upstream)

    assert plan.items == []
    assert any("up to date with upstream" in note for note in plan.unchanged)


def test_an_unchecked_upstream_falls_back_to_the_registry(tmp_path) -> None:
    store = _state(tmp_path)
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, checked=False,
        reason="upstream could not be checked: ConnectError",
    )}

    plan = build_update_plan(store, [_registry_component("c" * 40)], upstream=upstream)

    assert [item.target_ref for item in plan.items] == ["c" * 40]
    assert plan.items[0].reason == "verified Registry reference changed"


def test_offline_planning_behaves_exactly_as_before(tmp_path) -> None:
    store = _state(tmp_path)

    assert build_update_plan(store, [_registry_component(INSTALLED)]).items == []
    assert build_update_plan(store, [_registry_component("c" * 40)]).items != []


def test_a_user_owned_component_is_never_updated(tmp_path) -> None:
    store = _state(tmp_path, ownership=Ownership.EXISTING)
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, latest_ref=HEAD,
        pinning="commit", checked=True,
    )}

    plan = build_update_plan(store, [_registry_component("c" * 40)], upstream=upstream)

    assert plan.items == []


def test_an_unrebuildable_component_is_reported_not_updated_blindly(tmp_path) -> None:
    """Without an install method there is nothing to apply, so upstream moving is only news."""
    store = _state(tmp_path, component_type=None, install_method=None, source_repository=None)
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, latest_ref=HEAD,
        pinning="commit", checked=True,
    )}

    plan = build_update_plan(store, [], upstream=upstream)

    assert plan.items == []
    assert any("cannot be rebuilt" in note for note in plan.unchanged)


def test_local_modification_is_warned_before_an_upstream_update(tmp_path) -> None:
    managed_file = tmp_path / "skill" / "SKILL.md"
    managed_file.parent.mkdir(parents=True)
    managed_file.write_text("edited by the user", encoding="utf-8")
    store = _state(tmp_path, file_hashes={str(managed_file): "0" * 64})
    upstream = {"someone-skills": UpstreamRef(
        component_id="someone-skills", current_ref=INSTALLED, latest_ref=HEAD,
        pinning="commit", checked=True,
    )}

    plan = build_update_plan(store, [], upstream=upstream)

    assert any("was modified after GrayOM installed it" in w for w in plan.items[0].warnings)
