from pathlib import Path

import typer
from InquirerPy import inquirer
from rich.console import Console

from grayom_agent_guidance.adapters import CodexAdapter
from grayom_agent_guidance.core import analyze_conflicts, analyze_security, recommend
from grayom_agent_guidance.registry import load_registry

from .interview import run_interview
from .ui import show_header, show_plan

app = typer.Typer(no_args_is_help=True, help="GrayOM AI Agent Environment Manager")
console = Console()


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        show_header(console)


@app.command()
def setup() -> None:
    """Build a recommendation Plan; no settings are changed before approval."""
    show_header(console)
    adapter = CodexAdapter()
    detected = adapter.detect()
    console.print(f"Codex detected: [{'green' if detected.detected else 'yellow'}]{detected.detected}[/]")
    answer = run_interview()
    plan = recommend(answer, load_registry())
    plan.conflicts = analyze_conflicts(plan.selected)
    plan.security_findings = analyze_security(plan.selected)
    show_plan(console, plan)
    approved = inquirer.confirm(message="Install all changes?", default=False).execute()
    if not approved:
        console.print("Cancelled. No Agent settings were changed.")
        raise typer.Exit()
    backup_root = Path.cwd() / ".grayom" / "backups" / "latest"
    manifest = adapter.backup(backup_root)
    console.print(f"Backup created: {manifest.root}")
    console.print("[yellow]Installation adapters are scaffolded; component mutation is not enabled in this increment.[/yellow]")


@app.command()
def doctor() -> None:
    """Inspect the Codex installation and configuration."""
    show_header(console)
    result = CodexAdapter().health_check()
    for check in result.checks:
        console.print(f"[{'green' if check.passed else 'red'}]{'PASS' if check.passed else 'FAIL'}[/] {check.name}: {check.message}")
    if not result.healthy:
        raise typer.Exit(code=1)


@app.command("recommend")
def recommend_only() -> None:
    """Run the interview and print a Plan without installing."""
    show_header(console)
    plan = recommend(run_interview(), load_registry())
    plan.conflicts = analyze_conflicts(plan.selected)
    plan.security_findings = analyze_security(plan.selected)
    show_plan(console, plan)


@app.command()
def rollback(path: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Reserved command for manifest-driven rollback."""
    console.print(f"Rollback manifest loading is not enabled yet: {path}")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
