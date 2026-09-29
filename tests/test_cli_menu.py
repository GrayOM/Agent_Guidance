from typer.testing import CliRunner

from grayom_agent_guidance.cli.main import app


def test_help_and_version_are_fast_and_non_networked(monkeypatch) -> None:
    monkeypatch.setattr(
        "grayom_agent_guidance.cli.main.discover_components_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert "0.2.0" in version.output
