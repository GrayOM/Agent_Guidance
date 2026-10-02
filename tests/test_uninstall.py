"""Removing what Agent Guidance installed, and refusing to remove anything else.

`rollback` reverses the last transaction, which is not an uninstall: it cannot reach a
component installed three runs ago and it reads a transaction manifest rather than the disk.
These cover the command that can, and above all the three things it must not do — delete a
component the user already had, delete a file they edited afterwards, or delete a registration
Agent Guidance never wrote.
"""

import hashlib
import json
from pathlib import Path

import tomlkit

from agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
from agent_guidance.core.uninstall import (
    SKIP_NOT_INSTALLED, SKIP_NOT_MANAGED, SKIP_UNKNOWN_RECORD, apply_uninstall, plan_uninstall,
)
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod, Ownership,
)
from agent_guidance.state import ManagedComponent, StateStore


def skill_component() -> Component:
    return Component(
        id="demo-pack", name="Demo Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/demo-pack",
        supported_agents={AgentType.CODEX, AgentType.CLAUDE_CODE},
        capabilities={Capability.SECURITY_ANALYSIS},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/example/demo-pack",
            ref="a" * 40,
        ),
    )


def mcp_component() -> Component:
    return Component(
        id="github", name="GitHub MCP", type=ComponentType.MCP,
        github_url="https://github.com/example/github-mcp",
        supported_agents={AgentType.CODEX, AgentType.CLAUDE_CODE},
        capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp"),
    )


def plant_skill(root: Path, component_id: str, name: str, body: str = "skill body") -> Path:
    directory = root / f"{component_id}--{name}"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(body, encoding="utf-8")
    (directory / ".agent-guidance-component.json").write_text(
        json.dumps({"component_id": component_id, "skill_name": name}), encoding="utf-8",
    )
    return directory


def hashes_of(*directories: Path) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in directories
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != ".agent-guidance-component.json"
    }


def store(tmp_path: Path, record: ManagedComponent) -> StateStore:
    state = StateStore(tmp_path / "state" / "components.json")
    state.document.components[record.component_id] = record
    return state


# --- what it removes -----------------------------------------------------------------


def test_a_skill_installed_for_both_agents_is_removed_from_both(tmp_path) -> None:
    codex, claude = CodexAdapter(tmp_path), ClaudeCodeAdapter(tmp_path)
    first = plant_skill(codex.skills_root, "demo-pack", "one")
    second = plant_skill(claude.skills_root, "demo-pack", "one")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        ownership=Ownership.AGENT_GUIDANCE_INSTALLED, transaction_id="t1",
        component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[first, second], file_hashes=hashes_of(first, second),
    ))

    plan = plan_uninstall(state)
    result = apply_uninstall(plan, {AgentType.CODEX: codex, AgentType.CLAUDE_CODE: claude}, state)

    assert not first.exists() and not second.exists()
    assert result.successful
    assert result.forgotten == ["demo-pack"]
    assert "demo-pack" not in StateStore(state.path).document.components


def test_removing_for_one_agent_leaves_the_other_installed(tmp_path) -> None:
    """A component two Agents share keeps its files until the last one leaves."""
    codex, claude = CodexAdapter(tmp_path), ClaudeCodeAdapter(tmp_path)
    first = plant_skill(codex.skills_root, "demo-pack", "one")
    second = plant_skill(claude.skills_root, "demo-pack", "one")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        ownership=Ownership.AGENT_GUIDANCE_INSTALLED, transaction_id="t1",
        component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[first, second], file_hashes=hashes_of(first, second),
    ))

    plan = plan_uninstall(state, agents=[AgentType.CLAUDE_CODE])
    assert [action.agent for action in plan.actions] == [AgentType.CLAUDE_CODE]
    assert plan.actions[0].keeps_files_for == [AgentType.CODEX]
    assert plan.actions[0].paths == [], "files are shared, so they stay while Codex uses them"

    apply_uninstall(plan, {AgentType.CODEX: codex, AgentType.CLAUDE_CODE: claude}, state)

    assert first.exists() and second.exists()
    remaining = StateStore(state.path).document.components["demo-pack"]
    assert remaining.agents == [AgentType.CODEX]


def test_only_the_registration_agent_guidance_wrote_is_removed(tmp_path) -> None:
    """An MCP can land under an alias, so the recorded name is the only safe target.

    Deleting by component id would take the user's own `github` server with it.
    """
    adapter = CodexAdapter(tmp_path)
    adapter.codex_home.mkdir(parents=True)
    adapter.config_path.write_text(
        '# keep me\nmodel = "gpt-5-codex"\n\n'
        '[mcp_servers.github]\ncommand = "node"\nargs = ["/mine.js"]\n\n'
        '[mcp_servers.github-agent-guidance]\nurl = "https://example.test/mcp"\n',
        encoding="utf-8",
    )
    state = store(tmp_path, ManagedComponent(
        component_id="github", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="GitHub MCP", component_type=ComponentType.MCP,
        install_method=mcp_component().install_method,
        source_repository="https://github.com/example/github-mcp",
        configured_mcp={AgentType.CODEX: ["github-agent-guidance"]},
    ))

    result = apply_uninstall(plan_uninstall(state), {AgentType.CODEX: adapter}, state)

    document = tomlkit.parse(adapter.config_path.read_text(encoding="utf-8"))
    assert "github" in document["mcp_servers"], "the user's own server must survive"
    assert "github-agent-guidance" not in document["mcp_servers"]
    assert result.removals[0].removed_mcp == ["github-agent-guidance"]
    assert "# keep me" in adapter.config_path.read_text(encoding="utf-8")
    assert document["model"] == "gpt-5-codex"


def test_a_claude_code_mcp_is_removed_from_its_own_config(tmp_path) -> None:
    adapter = ClaudeCodeAdapter(tmp_path)
    adapter.config_path.write_text(
        json.dumps({"projects": {"keep": 1}, "mcpServers": {"github": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )
    state = store(tmp_path, ManagedComponent(
        component_id="github", agents=[AgentType.CLAUDE_CODE], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="GitHub MCP", component_type=ComponentType.MCP,
        install_method=mcp_component().install_method,
        source_repository="https://github.com/example/github-mcp",
        configured_mcp={AgentType.CLAUDE_CODE: ["github"]},
    ))

    apply_uninstall(plan_uninstall(state), {AgentType.CLAUDE_CODE: adapter}, state)

    document = json.loads(adapter.config_path.read_text(encoding="utf-8"))
    assert document["mcpServers"] == {}
    assert document["projects"] == {"keep": 1}, "unrelated keys are not an uninstall's business"


# --- what it refuses to remove -------------------------------------------------------


def test_a_file_the_user_edited_after_install_is_kept_and_reported(tmp_path) -> None:
    """The hash recorded at install time is what makes this decidable.

    Deleting a directory the user has since edited would destroy their work, so the
    component stays recorded for that Agent and the reason is reported.
    """
    adapter = CodexAdapter(tmp_path)
    kept = plant_skill(adapter.skills_root, "demo-pack", "edited")
    removed = plant_skill(adapter.skills_root, "demo-pack", "untouched")
    recorded = hashes_of(kept, removed)
    (kept / "SKILL.md").write_text("skill body\nmy own note\n", encoding="utf-8")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[kept, removed], file_hashes=recorded,
    ))

    result = apply_uninstall(plan_uninstall(state), {AgentType.CODEX: adapter}, state)

    assert kept.exists() and not removed.exists()
    note = " ".join(result.removals[0].preserved)
    assert "was edited after install" in note
    # The message has to point at the directory, because this is the one case where uninstall
    # finishes and still leaves files on disk, and only the user can decide what to do.
    assert str(kept) in note and "by hand" in note
    assert "demo-pack" in StateStore(state.path).document.components, (
        "a component with files still on disk has to stay recorded, or the next run "
        "installs a second copy beside it"
    )


def test_a_file_the_user_added_to_a_managed_skill_keeps_the_directory(tmp_path) -> None:
    adapter = CodexAdapter(tmp_path)
    directory = plant_skill(adapter.skills_root, "demo-pack", "one")
    recorded = hashes_of(directory)
    (directory / "notes.md").write_text("mine", encoding="utf-8")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[directory], file_hashes=recorded,
    ))

    result = apply_uninstall(plan_uninstall(state), {AgentType.CODEX: adapter}, state)

    assert directory.exists()
    assert any("was added" in note for note in result.removals[0].preserved)


def test_a_directory_without_agent_guidances_marker_is_never_deleted(tmp_path) -> None:
    """State can name a path that is no longer Agent Guidance's; the marker is the final word."""
    adapter = CodexAdapter(tmp_path)
    foreign = adapter.skills_root / "demo-pack--one"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("someone else's", encoding="utf-8")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[foreign],
    ))

    result = apply_uninstall(plan_uninstall(state), {AgentType.CODEX: adapter}, state)

    assert foreign.exists()
    assert any("no Agent Guidance marker" in note for note in result.removals[0].preserved)


def test_a_component_that_was_already_there_is_not_agent_guidances_to_remove(tmp_path) -> None:
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX], ownership=Ownership.EXISTING,
        transaction_id="t1", component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
    ))

    plan = plan_uninstall(state)

    assert plan.empty
    assert plan.skipped["demo-pack"] == SKIP_NOT_MANAGED


def test_a_record_predating_the_tracked_fields_is_left_alone(tmp_path) -> None:
    """Without the install method and type there is no exact inverse, so Agent Guidance declines."""
    state = store(tmp_path, ManagedComponent(
        component_id="legacy", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t0",
    ))

    plan = plan_uninstall(state)

    assert plan.empty
    assert plan.skipped["legacy"] == SKIP_UNKNOWN_RECORD


def test_naming_an_agent_that_does_not_have_it_removes_nothing(tmp_path) -> None:
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="t1", component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
    ))

    plan = plan_uninstall(state, agents=[AgentType.CLAUDE_CODE])

    assert plan.empty
    assert plan.skipped["demo-pack"] == SKIP_NOT_INSTALLED


def test_an_unknown_component_is_named_rather_than_ignored(tmp_path) -> None:
    state = StateStore(tmp_path / "state" / "components.json")

    plan = plan_uninstall(state, ["never-installed"])

    assert plan.skipped["never-installed"] == "not managed by Agent Guidance"


def test_the_other_agents_directories_are_not_this_agents_to_account_for(tmp_path) -> None:
    """State keeps one path list per component across Agents.

    Handing the whole list to each adapter made each one try to delete the other's
    directories, which the path validator refused — correctly, but as an error rather than
    as "not mine". Found by running an uninstall of a component installed for both Agents.
    """
    codex, claude = CodexAdapter(tmp_path), ClaudeCodeAdapter(tmp_path)
    mine = plant_skill(codex.skills_root, "demo-pack", "one")
    theirs = plant_skill(claude.skills_root, "demo-pack", "one")
    state = store(tmp_path, ManagedComponent(
        component_id="demo-pack", agents=[AgentType.CODEX, AgentType.CLAUDE_CODE],
        ownership=Ownership.AGENT_GUIDANCE_INSTALLED, transaction_id="t1",
        component_name="Demo Pack", component_type=ComponentType.SKILL,
        install_method=skill_component().install_method,
        source_repository="https://github.com/example/demo-pack",
        installation_paths=[mine, theirs], file_hashes=hashes_of(mine, theirs),
    ))

    result = apply_uninstall(
        plan_uninstall(state), {AgentType.CODEX: codex, AgentType.CLAUDE_CODE: claude}, state,
    )

    assert not result.errors, result.errors
    for removal in result.removals:
        assert removal.owned_paths == 1, "each Agent owns one of the two recorded directories"


def test_codex_reports_that_it_has_no_plugin_to_remove(tmp_path) -> None:
    component = Component(
        id="some-plugin", name="Some Plugin", type=ComponentType.PLUGIN,
        github_url="https://github.com/example/plug",
        supported_agents={AgentType.CLAUDE_CODE}, capabilities={Capability.CODE_REVIEW},
        install_method=InstallMethod(
            kind=InstallKind.PLUGIN_MARKETPLACE, plugin_id="p@m", marketplace="m",
        ),
    )

    result = CodexAdapter(tmp_path).remove_component(component, [], {}, [], [])

    assert not result.changed
    assert any("no plugins" in note for note in result.preserved)
