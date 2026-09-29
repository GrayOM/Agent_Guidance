import json

from grayom_agent_guidance.adapters import CursorAdapter
from grayom_agent_guidance.models import AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod


def test_cursor_uses_only_agent_configuration_paths(tmp_path) -> None:
    adapter = CursorAdapter(tmp_path / "home")
    component = Component(
        id="remote", name="Remote", type=ComponentType.MCP,
        github_url="https://github.com/example/remote", supported_agents={AgentType.CURSOR},
        capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(
            kind=InstallKind.MCP_HTTP, url="https://example.test/mcp",
            bearer_token_env_var="TOKEN",
        ),
    )
    adapter.configure_mcp(component)
    config = json.loads(adapter.config_path.read_text(encoding="utf-8"))
    assert adapter.get_config_paths() == [adapter.cursor_home / "mcp.json"]
    assert config["mcpServers"]["remote"]["headers"]["Authorization"] == "Bearer ${env:TOKEN}"
