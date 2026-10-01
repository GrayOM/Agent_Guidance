from typer.testing import CliRunner

from grayom_agent_guidance.cli.main import app
from grayom_agent_guidance.core.discovery import DiscoveryResult
from grayom_agent_guidance.models import AgentInstallation, AgentType, InterviewAnswer, SetupMode, WorkDomain
from grayom_agent_guidance.registry import load_registry
from grayom_agent_guidance.sources.base import SourceResult


def test_dry_run_creates_no_backup_or_state(monkeypatch, tmp_path) -> None:
    root = tmp_path / "grayom"
    monkeypatch.setattr("grayom_agent_guidance.cli.main.grayom_home", lambda: root)
    monkeypatch.setattr("grayom_agent_guidance.cli.main.detect_agents", lambda: [
        AgentInstallation(agent=AgentType.CODEX, detected=True),
        AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=False),
    ])
    monkeypatch.setattr("grayom_agent_guidance.cli.main.run_interview", lambda detected: InterviewAnswer(
        agents=[AgentType.CODEX], domains=[WorkDomain.GENERAL_DEVELOPMENT], mode=SetupMode.MINIMAL,
    ))
    candidates = load_registry()
    monkeypatch.setattr(
        "grayom_agent_guidance.cli.main.discover_components_sync",
        lambda *args, **kwargs: DiscoveryResult(
            candidates=candidates,
            sources=[SourceResult(source="registry", checked=True, discovered=len(candidates), validated=len(candidates))],
        ),
    )
    result = CliRunner().invoke(app, ["setup", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert not root.exists()
