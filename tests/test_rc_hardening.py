import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
from agent_guidance.errors import ConfigurationError
from agent_guidance.models import AgentType, Capability, Component, ComponentType, InstallKind, InstallMethod
from agent_guidance.runtime import (
    OperationLock, OperationLockedError, PathSecurityError, ProcessRunner,
    ProcessTimeoutError, validate_managed_path,
)
from agent_guidance.runtime.lock import _pid_alive
from agent_guidance.state import StateStore


FIXTURES = Path(__file__).parent / "fixtures"


def mcp(agent: AgentType) -> Component:
    return Component(
        id="agent-guidance-test", name="Agent Guidance Test", type=ComponentType.MCP,
        github_url="https://github.com/example/agent-guidance-test", supported_agents={agent},
        capabilities={Capability.REPOSITORY_ACCESS},
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp"),
    )


@pytest.mark.parametrize(
    ("agent", "adapter_type", "relative", "unknown_key"),
    [
        (AgentType.CODEX, CodexAdapter, Path(".codex/config.toml"), "custom-model"),
        (AgentType.CLAUDE_CODE, ClaudeCodeAdapter, Path(".claude.json"), "projects"),
    ],
)
def test_complex_fixture_preserves_unrelated_settings(tmp_path, agent, adapter_type, relative, unknown_key) -> None:
    source_name = "config.toml" if agent == AgentType.CODEX else ".claude.json"
    source = FIXTURES / agent.value / "complex" / source_name
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    adapter = adapter_type(tmp_path)
    adapter.configure_mcp(mcp(agent))
    assert unknown_key in target.read_text(encoding="utf-8")
    assert "agent-guidance-test" in target.read_text(encoding="utf-8")


def test_operation_lock_rejects_concurrent_owner_and_recovers_stale_lock(tmp_path) -> None:
    path = tmp_path / "agent-guidance.lock"
    with OperationLock(path, "setup"):
        with pytest.raises(OperationLockedError):
            OperationLock(path, "update").acquire()
    path.write_text(json.dumps({"pid": 99999999, "owner": "dead"}), encoding="utf-8")
    with OperationLock(path, "doctor"):
        assert path.exists()
    assert not path.exists()


def test_current_pid_is_alive_without_signalling_process() -> None:
    assert _pid_alive(os.getpid())


def test_path_validation_rejects_escape_and_symlink(tmp_path) -> None:
    root = tmp_path / "managed"
    root.mkdir()
    with pytest.raises(PathSecurityError):
        validate_managed_path(tmp_path / "outside", root)
    link = root / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PathSecurityError):
        validate_managed_path(link / "file", root)


def test_process_runner_timeout_and_secret_redaction() -> None:
    runner = ProcessRunner()
    with pytest.raises(ProcessTimeoutError):
        runner.run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    result = runner.run([sys.executable, "-c", "print('Bearer secret-value')"])
    assert "secret-value" not in result.stdout


def test_future_state_schema_is_not_overwritten(tmp_path) -> None:
    path = tmp_path / "components.json"
    original = '{"schema_version": 999, "components": {}}'
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        StateStore(path)
    assert path.read_text(encoding="utf-8") == original


def test_adapter_capabilities_are_explicit(tmp_path) -> None:
    assert CodexAdapter(tmp_path).capabilities.model_dump() == {
        "skills": True, "mcp": True, "plugins": False,
        "config_merge": True, "health_probe": True,
    }
    # Plugin support depends on Claude Code's CLI being present, so both states are stated
    # explicitly rather than inherited from whatever is on this machine's PATH.
    from agent_guidance.adapters.claude_plugins import ClaudePluginCli

    present = ClaudeCodeAdapter(tmp_path, plugins=ClaudePluginCli(executable="/usr/bin/claude"))
    assert present.capabilities.plugins

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("agent_guidance.adapters.claude_plugins.shutil.which", lambda _: None)
        assert not ClaudeCodeAdapter(tmp_path).capabilities.plugins
