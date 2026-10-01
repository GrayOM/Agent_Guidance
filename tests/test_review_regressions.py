"""Regressions for defects found while auditing the implementation against architecture.md."""

import json
import stat
import sys

import pytest
from pydantic import ValidationError

from grayom_agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
from grayom_agent_guidance.adapters.codex import MCP_DIFFERENT_SETTINGS_REASON
from grayom_agent_guidance.core.discovery import _merge_candidates
from grayom_agent_guidance.core.query_builder import build_queries
from grayom_agent_guidance.errors import ConfigurationError
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod,
    MultiAgentManifest, Ownership, SourceType, TrustMetadata,
)
from grayom_agent_guidance.observability import EventLogger
from grayom_agent_guidance.runtime import PathSecurityError
from grayom_agent_guidance.sources.base import RawCandidate
from grayom_agent_guidance.sources.normalizer import _component_type
from grayom_agent_guidance.sources.validator import ComponentValidator
from grayom_agent_guidance.state import ManagedComponent, StateStore


def _skill(component_id: str = "owner-repo", agents=None) -> Component:
    return Component(
        id=component_id, name="Demo", type=ComponentType.SKILL,
        github_url="https://github.com/Owner/Repo",
        capabilities={Capability.TESTING},
        supported_agents=agents if agents is not None else {AgentType.CLAUDE_CODE},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/Owner/Repo", ref="a" * 40,
        ),
    )


def test_candidate_supporting_one_selected_agent_stays_recommendable() -> None:
    """architecture.md 2/6: per-Agent applicability is decided in the Plan, not at discovery."""
    component = _skill(agents={AgentType.CLAUDE_CODE})
    validated = ComponentValidator({AgentType.CODEX, AgentType.CLAUDE_CODE}).validate(component)

    assert validated.recommendable
    assert any("not applied to: codex" == warning for warning in validated.validation_warnings)


def test_candidate_supporting_no_selected_agent_is_rejected() -> None:
    component = _skill(agents={AgentType.CURSOR})
    validated = ComponentValidator({AgentType.CODEX}).validate(component)

    assert not validated.recommendable
    assert "no selected Agent is supported by this component" in validated.validation_warnings


def test_claude_skill_lookup_matches_the_installed_directory_name(tmp_path) -> None:
    """The existence probe must use the same _safe_name normalisation as the installer."""
    adapter = ClaudeCodeAdapter(home=tmp_path / "home")
    installed = adapter.skills_root / "owner-repo--my-skill"
    installed.mkdir(parents=True)
    installed.joinpath("SKILL.md").write_text(
        "---\nname: my skill\ndescription: d\n---\n", encoding="utf-8",
    )
    component = _skill("owner-repo")

    codex = CodexAdapter(home=tmp_path / "home")
    codex.skills_root.mkdir(parents=True, exist_ok=True)
    (codex.skills_root / "owner-repo--my-skill").mkdir()
    (codex.skills_root / "owner-repo--my-skill" / "SKILL.md").write_text(
        "---\nname: my skill\ndescription: d\n---\n", encoding="utf-8",
    )

    assert adapter.existing_component_status(component) == (
        True, "existing Claude Code Skill preserved",
    )
    # Both adapters install under _safe_name, so neither may report a repeated setup as new.
    assert codex.existing_component_status(component)[0] is True


def test_every_adapter_reports_an_incompatible_mcp_with_the_shared_reason(tmp_path) -> None:
    """Reconciliation matches this reason exactly, so adapters must not reword it."""
    mcp = Component(
        id="github", name="GitHub", type=ComponentType.MCP,
        github_url="https://github.com/github/github-mcp-server",
        supported_agents={AgentType.CLAUDE_CODE},
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp/"),
    )
    adapter = ClaudeCodeAdapter(home=tmp_path / "home")
    adapter.config_path.parent.mkdir(parents=True, exist_ok=True)
    adapter.config_path.write_text(
        json.dumps({"mcpServers": {"github": {"type": "http", "url": "https://user.test/mcp"}}}),
        encoding="utf-8",
    )

    assert adapter.existing_component_status(mcp) == (True, MCP_DIFFERENT_SETTINGS_REASON)


def test_manifest_written_by_a_newer_schema_is_refused(tmp_path) -> None:
    """architecture.md 10: state, cache and manifest must all reject a future schema."""
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps({
        "schema_version": 99, "transaction_id": "t", "root": str(tmp_path),
        "selected_agents": ["codex"], "state": "COMMITTED",
    }), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        MultiAgentManifest.load(target)


def test_component_id_cannot_escape_the_managed_state_directory(tmp_path) -> None:
    with pytest.raises(ValidationError):
        _skill("../../../escape")

    store = StateStore(tmp_path / "state" / "components.json")
    store.document.components["../escape"] = ManagedComponent(
        component_id="../escape", agents=[AgentType.CODEX],
        ownership=Ownership.GRAYOM_INSTALLED, transaction_id="t",
    )
    with pytest.raises(PathSecurityError):
        store.save()
    assert not (tmp_path / "state" / "escape.json").exists()


def test_search_queries_cover_every_inferred_capability() -> None:
    """A single alphabetically-first capability is not a comprehensive GitHub search."""
    capabilities = {
        Capability.VULNERABILITY_RESEARCH, Capability.SECURITY_ANALYSIS,
        Capability.SOURCE_ANALYSIS, Capability.BROWSER_AUTOMATION,
    }
    queries = build_queries([AgentType.CLAUDE_CODE], capabilities, ComponentType.MCP, limit=5)

    assert len(queries) == 5
    for term in ("vulnerability research", "security analysis", "source code analysis"):
        assert any(f'"{term}"' in query for query in queries), term


def test_a_truncated_query_budget_keeps_the_specialised_capabilities() -> None:
    """Alphabetical selection dropped 'vulnerability research' for a vulnerability profile."""
    capabilities = {
        Capability.VULNERABILITY_RESEARCH, Capability.SECURITY_ANALYSIS,
        Capability.BROWSER_AUTOMATION, Capability.TESTING, Capability.CODE_EDITING,
    }
    queries = build_queries([AgentType.CODEX], capabilities, ComponentType.SKILL, limit=3)

    assert any('"security analysis"' in query for query in queries)
    assert not any('"browser automation"' in query for query in queries)


def test_merge_is_independent_of_the_order_sources_return_in() -> None:
    """architecture.md 5: identical inputs must merge identically whatever the arrival order."""
    def candidate(component_id: str) -> Component:
        return Component(
            id=component_id, name=component_id, type=ComponentType.SKILL,
            github_url="https://github.com/Owner/Repo", source="github",
            capabilities={Capability.TESTING}, supported_agents={AgentType.CODEX},
            trust=TrustMetadata(source_type=SourceType.GITHUB),
            install_method=InstallMethod(
                kind=InstallKind.GIT_SKILLS, repository="https://github.com/Owner/Repo", ref="a",
            ),
        )

    forward = _merge_candidates([candidate("alpha"), candidate("beta")])
    reverse = _merge_candidates([candidate("beta"), candidate("alpha")])

    assert [item.id for item in forward] == [item.id for item in reverse]


def test_incidental_plugin_manifest_does_not_reclassify_a_skill_repository() -> None:
    raw = RawCandidate(
        repository_full_name="owner/repo", repository_url="https://github.com/owner/repo",
        source_type=SourceType.GITHUB,
        tree_paths=["skills/demo/SKILL.md", "examples/plugin.json"],
    )

    assert _component_type(raw, "") == ComponentType.SKILL


def test_event_log_does_not_expose_a_secret_it_was_given(tmp_path) -> None:
    log = tmp_path / "logs" / "grayom.jsonl"
    EventLogger(path=log).write("setup_complete", token="ghp_secret")

    assert "ghp_secret" not in log.read_text(encoding="utf-8")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows reports 0o666 for any writable file; it uses ACLs, not POSIX mode bits",
)
def test_event_log_is_created_without_group_or_world_access(tmp_path) -> None:
    """The log was created under the default umask and chmoded only afterwards."""
    log = tmp_path / "logs" / "grayom.jsonl"
    EventLogger(path=log).write("setup_complete", token="ghp_secret")

    assert stat.S_IMODE(log.stat().st_mode) & 0o077 == 0


def test_shared_runtime_warnings_reach_the_transaction_manifest(tmp_path) -> None:
    """architecture.md 7: a missing STDIO runtime is reported, never silently dropped."""
    from grayom_agent_guidance.core.shared_components import SharedComponentManager
    from grayom_agent_guidance.models import DependencyRequirement, SharedComponentRecord

    component = Component(
        id="needs-runtime", name="Needs Runtime", type=ComponentType.MCP,
        github_url="https://github.com/owner/mcp",
        supported_agents={AgentType.CODEX},
        install_method=InstallMethod(
            kind=InstallKind.MCP_STDIO, command="grayom-absent-runtime",
        ),
        dependencies=[DependencyRequirement(
            name="Absent", executable="grayom-absent-runtime", required=True,
        )],
    )
    record = SharedComponentRecord(
        component_id="needs-runtime", ownership=Ownership.SHARED, shared=True,
        used_by=[AgentType.CODEX],
    )
    manifest = MultiAgentManifest(root=tmp_path, selected_agents=[AgentType.CODEX])
    manifest.shared_warnings.extend(SharedComponentManager().prepare(component, record))

    assert manifest.shared_warnings == [
        "Needs Runtime dependency is unavailable: grayom-absent-runtime"
    ]
