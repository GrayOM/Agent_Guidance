import tomllib

from agent_guidance.adapters import CodexAdapter
from agent_guidance.models import AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod


def mcp_component() -> Component:
    return Component(
        id="github", name="GitHub", type=ComponentType.MCP,
        github_url="https://github.com/github/github-mcp-server",
        supported_agents={AgentType.CODEX}, capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp"),
    )


def test_same_mcp_setup_twice_does_not_rewrite_or_duplicate(tmp_path) -> None:
    adapter = CodexAdapter(tmp_path / "home")
    first = adapter.configure_mcp(mcp_component())
    before = adapter.config_path.read_bytes()
    second = adapter.configure_mcp(mcp_component())
    assert first.changed and not second.changed
    assert adapter.config_path.read_bytes() == before
    assert list(tomllib.loads(before.decode())["mcp_servers"]) == ["github"]
