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
    assert "0.1.0" in version.output


def test_the_plan_table_shows_only_what_will_be_installed() -> None:
    """A live run put ten "Skipped" rows around the two components that mattered."""
    from rich.console import Console
    from grayom_agent_guidance.cli.ui import show_plan
    from grayom_agent_guidance.models import (
        AgentType, Capability, Component, ComponentType, InterviewAnswer, RecommendationItem,
        RecommendationPlan, SetupMode, WorkDomain,
    )

    def _component(name: str) -> Component:
        return Component(
            id=name, name=name, type=ComponentType.SKILL,
            github_url=f"https://github.com/example/{name}",
            capabilities={Capability.TESTING}, supported_agents={AgentType.CODEX},
        )

    plan = RecommendationPlan(
        interview=InterviewAnswer(
            agents=[AgentType.CODEX], domains=[WorkDomain.GENERAL_DEVELOPMENT],
            mode=SetupMode.MINIMAL,
        ),
        capabilities={Capability.TESTING},
        items=[
            RecommendationItem(component=_component("kept"), selected=True, reasons=["covers: testing"]),
            RecommendationItem(component=_component("skipped-a"), selected=False,
                               reasons=["not relevant to inferred capabilities"]),
            RecommendationItem(component=_component("skipped-b"), selected=False,
                               reasons=["not relevant to inferred capabilities"]),
            RecommendationItem(component=_component("skipped-c"), selected=False,
                               reasons=["conflicts with kept"]),
        ],
    )
    console = Console(record=True, width=200)
    show_plan(console, plan)
    output = console.export_text()

    assert "kept" in output
    assert "skipped-a" not in output and "skipped-c" not in output
    assert "3 other candidates considered" in output
    assert "2 not relevant to inferred capabilities" in output
    assert "1 conflicts with kept" in output
