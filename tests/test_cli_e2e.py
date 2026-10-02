from types import SimpleNamespace

from typer.testing import CliRunner

from agent_guidance.adapters import CodexAdapter
from agent_guidance.cli.main import app
from agent_guidance.core.discovery import DiscoveryResult
from agent_guidance.models import (
    AgentInstallation, AgentType, Capability, Component, ComponentType, InterviewAnswer,
    InstallKind, InstallMethod, SetupMode, WorkDomain,
)
from agent_guidance.sources.base import SourceResult


def test_setup_rerun_doctor_update_and_rollback(tmp_path, monkeypatch) -> None:
    agent_guidance_root = tmp_path / "agent-guidance"
    agent_home = tmp_path / "agent-home"
    adapter = CodexAdapter(agent_home)
    answer = InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.GENERAL_DEVELOPMENT], mode=SetupMode.MINIMAL,
    )
    component = Component(
        id="local-http", name="Local HTTP MCP", type=ComponentType.MCP,
        github_url="https://github.com/example/local-http", supported_agents={AgentType.CODEX},
        capabilities=set(Capability), official=True,
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://example.test/mcp"),
    )
    detected = [AgentInstallation(agent=AgentType.CODEX, detected=True)]
    discovery = DiscoveryResult(
        candidates=[component],
        sources=[SourceResult(source="registry", checked=True, discovered=1, validated=1)],
    )
    monkeypatch.setattr("agent_guidance.cli.main.agent_guidance_home", lambda: agent_guidance_root)
    monkeypatch.setattr("agent_guidance.state.agent_guidance_home", lambda: agent_guidance_root)
    monkeypatch.setattr("agent_guidance.cli.main.detect_agents", lambda: detected)
    monkeypatch.setattr("agent_guidance.cli.main._adapter_map", lambda home=None: {AgentType.CODEX: adapter})
    monkeypatch.setattr("agent_guidance.cli.main.run_interview", lambda items: answer)
    monkeypatch.setattr("agent_guidance.cli.main.discover_components_sync", lambda *args, **kwargs: discovery)
    monkeypatch.setattr(
        "agent_guidance.cli.main.inquirer.confirm",
        lambda **kwargs: SimpleNamespace(execute=lambda: True),
    )

    runner = CliRunner()
    first = runner.invoke(app, ["setup", "--offline", "--no-probe-mcp"])
    assert first.exit_code == 0, first.output
    assert "Installation completed" in first.output
    assert adapter.config_path.exists()

    second = runner.invoke(app, ["setup", "--offline", "--no-probe-mcp"])
    assert second.exit_code == 0, second.output
    assert "No installation required" in second.output

    doctor = runner.invoke(app, ["doctor", "--no-probe-mcp"])
    assert doctor.exit_code == 0, doctor.output
    assert "Overall: PASS" in doctor.output

    update = runner.invoke(app, ["update", "--yes"])
    assert update.exit_code == 0, update.output
    assert "up to date" in update.output

    rolled_back = runner.invoke(app, ["rollback", "--yes"])
    assert rolled_back.exit_code == 0, rolled_back.output
    assert "Rollback completed" in rolled_back.output
    assert not adapter.config_path.exists()
