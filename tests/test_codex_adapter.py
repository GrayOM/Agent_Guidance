import json
import tomllib

from agent_guidance.adapters import CodexAdapter
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod,
)


def mcp_component() -> Component:
    return Component(
        id="github", name="GitHub MCP", type=ComponentType.MCP,
        github_url="https://github.com/github/github-mcp-server",
        supported_agents={AgentType.CODEX}, capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(
            kind=InstallKind.MCP_HTTP, url="https://api.githubcopilot.com/mcp/",
            bearer_token_env_var="GITHUB_PAT_TOKEN",
        ),
    )


def skill_component() -> Component:
    return Component(
        id="demo-pack", name="Demo Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/demo", supported_agents={AgentType.CODEX},
        capabilities={Capability.CODE_EDITING},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/example/demo", ref="abc123",
        ),
    )


def test_existing_codex_config_is_merged_and_matching_mcp_is_not_duplicated(tmp_path) -> None:
    home = tmp_path / "home"
    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('# keep this comment\nmodel = "existing"\n', encoding="utf-8")
    adapter = CodexAdapter(home=home)

    first = adapter.configure_mcp(mcp_component())
    second = adapter.configure_mcp(mcp_component())
    parsed = tomllib.loads(config.read_text(encoding="utf-8"))

    assert first.changed
    assert not second.changed
    assert parsed["model"] == "existing"
    assert parsed["mcp_servers"]["github"]["url"] == "https://api.githubcopilot.com/mcp/"
    assert config.read_text(encoding="utf-8").count("[mcp_servers.github]") == 1
    assert "# keep this comment" in config.read_text(encoding="utf-8")
    exists, reason = adapter.existing_component_status(mcp_component())
    assert exists and "preserved" in reason


def test_different_existing_mcp_is_detected_without_overwrite(tmp_path) -> None:
    adapter = CodexAdapter(home=tmp_path / "home")
    adapter.codex_home.mkdir(parents=True)
    adapter.config_path.write_text(
        '[mcp_servers.github]\nurl = "https://user.example/mcp"\n', encoding="utf-8",
    )
    exists, reason = adapter.existing_component_status(mcp_component())
    assert exists and "different settings" in reason
    assert "user.example" in adapter.config_path.read_text(encoding="utf-8")


def test_skill_install_discovers_valid_skill_and_preserves_existing(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    source = tmp_path / "source"
    skill = source / "skills" / "demo"
    skill.mkdir(parents=True)
    skill.joinpath("SKILL.md").write_text(
        "---\nname: Demo\ndescription: Test skill\n---\nDo the work.\n", encoding="utf-8",
    )
    adapter = CodexAdapter(home=home)
    # Cloning is now the one shared implementation both Agents install through.
    monkeypatch.setattr(
        "agent_guidance.adapters.json_support.clone_pinned",
        lambda component, destination: source,
    )

    first = adapter.install_skill(skill_component())
    target = home / ".agents" / "skills" / "demo-pack--demo"
    marker = json.loads((target / ".agent-guidance-component.json").read_text(encoding="utf-8"))
    second = adapter.install_skill(skill_component())

    assert first.changed and target in first.created_paths
    assert marker["component_id"] == "demo-pack"
    assert not second.changed and target in second.preserved_paths


def test_health_check_parses_config_discovers_skill_and_mcp(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    adapter = CodexAdapter(home=home)
    adapter.codex_home.mkdir(parents=True)
    adapter.configure_mcp(mcp_component())
    target = adapter.skills_root / "demo-pack--demo"
    target.mkdir(parents=True)
    target.joinpath("SKILL.md").write_text(
        "---\nname: Demo\ndescription: Test skill\n---\n", encoding="utf-8",
    )
    target.joinpath(".agent-guidance-component.json").write_text(
        json.dumps({"component_id": "demo-pack"}), encoding="utf-8",
    )
    monkeypatch.setattr(adapter, "_probe_http_mcp", lambda server_id, config: (True, "discovered 10 tools"))

    result = adapter.health_check([skill_component(), mcp_component()])
    assert result.healthy
    assert all(check.passed for check in result.checks)


def test_removing_an_mcp_server_leaves_the_trailing_newlines_alone(tmp_path) -> None:
    """`uninstall` has to put the file back to the byte, and it did not.

    Removing a table leaves the blank line that separated it behind, so a config ending in one
    newline came back from an uninstall ending in two. Trailing whitespace means nothing in
    TOML, but "uninstall puts your config back" is a promise about the file, and the real-Agent
    check compares it byte for byte.
    """
    from agent_guidance.adapters.codex import CodexAdapter

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    config = home / ".codex" / "config.toml"
    original = (
        '# mine\nmodel = "o3"\n\n'
        '[mcp_servers.mine]\ncommand = "python3"\n\n'
        '[mcp_servers.theirs]\ncommand = "npx"\n'
    )
    config.write_text(original, encoding="utf-8")

    adapter = CodexAdapter(home)
    removed = adapter._remove_toml_mcp(["theirs"], _removal_result())

    assert removed == ["theirs"]
    after = config.read_text(encoding="utf-8")
    assert "theirs" not in after
    assert "# mine" in after and "mcp_servers.mine" in after
    assert after.endswith('command = "python3"\n'), repr(after)


def test_a_config_kept_without_a_final_newline_stays_that_way(tmp_path) -> None:
    """The file's own ending is restored, not normalised.

    Rendering always ends in one newline, so the obvious fix — strip and add one — would have
    quietly added a final newline to a file the user keeps without one. That is still editing
    someone's file for reasons they did not ask for.
    """
    from agent_guidance.adapters.codex import CodexAdapter

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    config = home / ".codex" / "config.toml"
    original = '[mcp_servers.mine]\ncommand = "python3"\n\n[mcp_servers.theirs]\ncommand = "npx"'
    config.write_text(original, encoding="utf-8")

    CodexAdapter(home)._remove_toml_mcp(["theirs"], _removal_result())

    assert config.read_text(encoding="utf-8") == '[mcp_servers.mine]\ncommand = "python3"'


def _removal_result():
    from agent_guidance.models import ComponentRemovalResult

    return ComponentRemovalResult(component_id="theirs")
