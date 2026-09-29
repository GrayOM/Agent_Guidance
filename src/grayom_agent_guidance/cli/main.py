import json
from pathlib import Path

import typer
from InquirerPy import inquirer
from rich.console import Console

from grayom_agent_guidance.adapters import CodexAdapter, detect_agents
from grayom_agent_guidance.core import (
    InstallationTransaction, analyze_conflicts, analyze_security,
    discover_components_sync, recommend,
)
from grayom_agent_guidance.models import Component, InstallationManifest
from grayom_agent_guidance.registry import load_registry

from .interview import run_interview
from .ui import show_detected_agents, show_discovery, show_header, show_health, show_plan

app = typer.Typer(no_args_is_help=False, help="GrayOM AI Agent Environment Manager")
console = Console()


def _build_plan(
    detected=None, adapter: CodexAdapter | None = None, *, offline: bool = False,
):
    answer = run_interview(detected)
    console.print("[bold]Searching components...[/bold]")
    discovery = discover_components_sync(answer, offline=offline)
    show_discovery(console, discovery)
    plan = recommend(answer, discovery.candidates)
    if adapter:
        for item in plan.items:
            if not item.selected:
                continue
            exists, reason = adapter.existing_component_status(item.component)
            if exists:
                item.selected = False
                item.reasons = [reason or "existing component preserved"]
    plan.conflicts = analyze_conflicts(plan.selected)
    plan.security_findings = analyze_security(plan.selected)
    return plan


def _run_setup(probe_mcp: bool = True, offline: bool = False) -> None:
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    codex = next(item for item in detected if item.agent.value == "codex")
    if not codex.detected:
        console.print("[red]Codex was not detected. GrayOM does not install Agent applications.[/red]")
        raise typer.Exit(code=1)

    adapter = CodexAdapter()
    preflight = adapter.health_check([], probe_mcp=False)
    if not preflight.healthy:
        console.print("[red]Codex preflight failed; no changes were made.[/red]")
        show_health(console, preflight)
        raise typer.Exit(code=1)
    plan = _build_plan(detected, adapter, offline=offline)
    show_plan(console, plan)
    approved = inquirer.confirm(message="Install all changes?", default=False).execute()
    if not approved:
        console.print("Cancelled. No Agent settings were changed.")
        raise typer.Exit()

    backup_root = Path.home() / ".grayom-agent-guidance" / "backups"
    result = InstallationTransaction(adapter, backup_root).execute(
        plan.selected, probe_mcp=probe_mcp,
    )
    if not result.success:
        console.print(f"[red]Installation failed: {result.error}[/red]")
        if result.rollback:
            state = "completed" if result.rollback.successful else "completed with errors"
            console.print(f"Rollback {state}.")
            for error in result.rollback.errors:
                console.print(f"[red]- {error}[/red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]Installation completed.[/bold green]")
    if result.health:
        show_health(console, result.health)
    console.print(f"Manifest: {result.manifest.path}")
    console.print(
        "Installed components: "
        + (", ".join(result.manifest.installed_components) or "None (all selected components already existed)")
    )
    console.print(f"Created Skill paths: {len(result.manifest.created_paths)}")
    console.print(
        "Configured MCP: " + (", ".join(result.manifest.configured_mcp) or "None")
    )
    if result.manifest.preexisting_components:
        console.print("Preserved existing components: " + ", ".join(result.manifest.preexisting_components))


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    """Run setup when no subcommand is supplied."""
    if ctx.invoked_subcommand is None:
        _run_setup()


@app.command()
def setup(
    probe_mcp: bool = typer.Option(
        True, "--probe-mcp/--no-probe-mcp", help="Attempt MCP initialize and tool discovery",
    ),
    offline: bool = typer.Option(False, "--offline", help="Use local registry and verified cache only"),
) -> None:
    """Recommend and install a Codex Agent environment transactionally."""
    _run_setup(probe_mcp=probe_mcp, offline=offline)


def _installed_registry_components(adapter: CodexAdapter) -> list[Component]:
    state = adapter.inspect()
    mcp_ids = set(state["mcp_servers"])
    skill_ids: set[str] = set()
    for path in state["skills"]:
        marker = path / ".grayom-component.json"
        if marker.exists():
            try:
                skill_ids.add(json.loads(marker.read_text(encoding="utf-8"))["component_id"])
            except (OSError, ValueError, KeyError):
                pass
    ids = mcp_ids | skill_ids
    return [component for component in load_registry() if component.id in ids]


@app.command()
def doctor(
    probe_mcp: bool = typer.Option(
        True, "--probe-mcp/--no-probe-mcp", help="Attempt MCP initialize and tool discovery",
    ),
) -> None:
    """Inspect Codex config, managed Skills, MCP startup and tool discovery."""
    show_header(console)
    adapter = CodexAdapter()
    result = adapter.health_check(_installed_registry_components(adapter), probe_mcp=probe_mcp)
    show_health(console, result)
    if not result.healthy:
        raise typer.Exit(code=1)


@app.command("recommend")
def recommend_only(
    offline: bool = typer.Option(False, "--offline", help="Use local registry and verified cache only"),
) -> None:
    """Run the interview and print a Plan without installing."""
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    show_plan(console, _build_plan(detected, offline=offline))


def _latest_manifest(root: Path) -> Path:
    candidates = sorted(root.glob("*/manifest.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no rollback manifests found in {root}")
    return candidates[0]


@app.command()
def rollback(
    path: Path | None = typer.Argument(None, help="Manifest file or backup directory; latest if omitted"),
) -> None:
    """Restore Codex config and remove only paths created by one GrayOM transaction."""
    root = Path.home() / ".grayom-agent-guidance" / "backups"
    try:
        manifest_path = path or _latest_manifest(root)
        manifest = InstallationManifest.load(manifest_path)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Cannot load rollback manifest: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    result = CodexAdapter().rollback(manifest)
    if result.successful:
        console.print("[green]Rollback completed.[/green]")
    else:
        for error in result.errors:
            console.print(f"[red]- {error}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
