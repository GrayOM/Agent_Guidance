import json

from agent_guidance.adapters import ClaudeCodeAdapter
from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod,
)


def mcp() -> Component:
    return Component(
        id="github", name="GitHub", type=ComponentType.MCP,
        github_url="https://github.com/github/github-mcp-server",
        supported_agents={AgentType.CLAUDE_CODE}, capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp"),
    )


def test_claude_mcp_merge_backup_and_rollback(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    adapter = ClaudeCodeAdapter(home)
    adapter.config_path.write_text('{"theme": "dark"}', encoding="utf-8")
    backup = adapter.backup(tmp_path / "backup")
    result = adapter.configure_mcp(mcp())
    parsed = json.loads(adapter.config_path.read_text(encoding="utf-8"))
    assert result.changed and parsed["theme"] == "dark"
    assert parsed["mcpServers"]["github"]["type"] == "http"
    from agent_guidance.models import InstallationManifest
    rolled_back = adapter.rollback(InstallationManifest(backup=backup))
    assert rolled_back.successful
    assert json.loads(adapter.config_path.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_claude_name_collision_preserves_user_entry(tmp_path) -> None:
    adapter = ClaudeCodeAdapter(tmp_path / "home")
    adapter.home.mkdir()
    adapter.config_path.write_text(
        '{"mcpServers":{"github":{"type":"http","url":"https://user.test/mcp"}}}',
        encoding="utf-8",
    )
    result = adapter.configure_mcp(mcp())
    parsed = json.loads(adapter.config_path.read_text(encoding="utf-8"))["mcpServers"]
    assert parsed["github"]["url"] == "https://user.test/mcp"
    assert parsed["github-agent-guidance"]["url"] == "https://example.test/mcp"
    assert result.configured_mcp == ["github-agent-guidance"]
    exists, reason = adapter.existing_component_status(mcp())
    assert exists and "alias" in reason
