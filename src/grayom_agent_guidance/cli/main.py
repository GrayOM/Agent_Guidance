import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from InquirerPy import inquirer
from rich.console import Console

from grayom_agent_guidance import __version__
from grayom_agent_guidance.adapters import (
    AgentAdapter, ClaudeCodeAdapter, CodexAdapter, CursorAdapter, detect_agents,
)
from grayom_agent_guidance.config import grayom_home, load_config
from grayom_agent_guidance.core import (
    MultiAgentInstallationTransaction, UpdateTransaction, analyze_conflicts,
    analyze_security, build_multi_agent_plan, build_update_plan, detect_platform,
    discover_components_sync, explain_plan, recommend, rollback_multi_agent,
)
from grayom_agent_guidance.errors import GrayOMError
from grayom_agent_guidance.models import (
    AgentInstallation, AgentType, Component, HealthCheckResult, InstallationManifest,
    MultiAgentManifest,
)
from grayom_agent_guidance.observability import EventLogger, redact
from grayom_agent_guidance.registry import load_registry
from grayom_agent_guidance.state import StateStore

from .interview import run_interview
from .ui import show_detected_agents, show_discovery, show_header, show_health, show_plan

app = typer.Typer(no_args_is_help=False, help="GrayOM AI Agent Environment Manager")
console = Console()
_verbose = False


def _adapter_map(home: Path | None = None) -> dict[AgentType, AgentAdapter]:
    return {
        AgentType.CODEX: CodexAdapter(home),
        AgentType.CLAUDE_CODE: ClaudeCodeAdapter(home),
        AgentType.CURSOR: CursorAdapter(home),
    }


def _friendly_error(exc: Exception, operation: str) -> None:
    if isinstance(exc, GrayOMError):
        message, reason, action = exc.user_message, exc.technical_message, exc.suggested_action
    else:
        message = f"GrayOM could not complete {operation}."
        reason = str(exc)
        action = "Run: grayom doctor"
    console.print(f"[red]{message}[/red]\n\nReason:\n{reason}\n\n{action}")
    EventLogger(verbose=_verbose).write("command_error", operation=operation, error=reason)
    if _verbose:
        console.print_exception()


def _build_plan(
    detected: list[AgentInstallation], adapters: dict[AgentType, AgentAdapter], *, offline: bool = False,
):
    answer = run_interview(detected)
    with console.status("Discovering and validating components..."):
        discovery = discover_components_sync(answer, offline=offline)
    show_discovery(console, discovery)
    plan = recommend(answer, discovery.candidates)
    plan.conflicts = analyze_conflicts(plan.selected)
    plan.security_findings = analyze_security(plan.selected)
    installation_map = {item.agent: item for item in detected}
    multi_plan = build_multi_agent_plan(plan, installation_map, adapters)
    return plan, multi_plan, explain_plan(plan)


def _run_setup(probe_mcp: bool = True, offline: bool = False, dry_run: bool = False) -> None:
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    if not any(item.detected for item in detected):
        console.print("[red]No supported Agent was detected. GrayOM does not install Agent applications.[/red]")
        raise typer.Exit(code=1)
    adapters = _adapter_map()
    try:
        plan, multi_plan, explanation = _build_plan(detected, adapters, offline=offline)
        show_plan(console, plan, multi_plan, explanation)
        changes = sum(len(agent_plan.components) for agent_plan in multi_plan.agents.values())
        if dry_run:
            console.print("\n[bold yellow]DRY RUN[/bold yellow]\nNo changes, backups, or installations were created.")
            return
        if changes == 0:
            console.print("[green]No installation required. Existing configuration already satisfies the Plan.[/green]")
            return
        approved = inquirer.confirm(message="Install all changes?", default=False).execute()
        if not approved:
            console.print("Cancelled. No Agent settings were changed.")
            return
        logger = EventLogger(verbose=_verbose)
        result = MultiAgentInstallationTransaction(
            {agent: adapters[agent] for agent in multi_plan.agents}, grayom_home() / "backups",
        ).execute(multi_plan, probe_mcp=probe_mcp)
        logger.write(
            "setup_complete", transaction_id=result.manifest.transaction_id,
            result="success" if result.success else "failed", error=result.error,
        )
        if not result.success:
            console.print(f"[red]Installation failed: {result.error}[/red]")
            for agent, rollback_result in result.rollbacks.items():
                state = "completed" if rollback_result.successful else "completed with errors"
                console.print(f"{agent.value} rollback {state}.")
                for error in rollback_result.errors:
                    console.print(f"[red]- {error}[/red]")
            raise typer.Exit(code=1)
        StateStore().record(multi_plan, result.manifest)
        console.print("\n[bold green]Installation completed.[/bold green]")
        for agent, health in result.health.items():
            console.print(f"\n[bold]{agent.value.replace('_', ' ').title()}[/bold]")
            show_health(console, health)
        console.print(f"Manifest: {result.manifest.path}")
    except typer.Exit:
        raise
    except Exception as exc:
        _friendly_error(exc, "Agent environment setup")
        raise typer.Exit(code=1) from exc


def _interactive_menu() -> None:
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    action = inquirer.select(message="What would you like to do?", choices=[
        {"name": "Setup Agent Environment", "value": "setup"},
        {"name": "Get Recommendations", "value": "recommend"},
        {"name": "Run Doctor", "value": "doctor"},
        {"name": "Check Updates", "value": "update"},
        {"name": "Rollback", "value": "rollback"},
        {"name": "Exit", "value": "exit"},
    ]).execute()
    if action == "setup":
        _run_setup()
    elif action == "recommend":
        recommend_only()
    elif action == "doctor":
        doctor()
    elif action == "update":
        update()
    elif action == "rollback":
        rollback()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit", is_eager=True),
    verbose: bool = typer.Option(False, "--verbose", help="Show technical error details"),
) -> None:
    """Open the interactive menu when no direct command is supplied."""
    global _verbose
    if version:
        console.print(f"GrayOM Agent Guidance {__version__}")
        raise typer.Exit()
    _verbose = verbose or load_config().ui.verbose
    if ctx.invoked_subcommand is None:
        _interactive_menu()


@app.command()
def setup(
    probe_mcp: bool = typer.Option(True, "--probe-mcp/--no-probe-mcp"),
    offline: bool = typer.Option(False, "--offline", help="Use Registry and verified cache only"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build the complete Plan without writing files"),
) -> None:
    """Reconcile and transactionally apply an Agent environment."""
    _run_setup(probe_mcp=probe_mcp, offline=offline, dry_run=dry_run)


def _state_components(state: StateStore, agent: AgentType) -> list[Component]:
    registry = {component.id: component for component in load_registry()}
    return [
        registry[item.component_id] for item in state.document.components.values()
        if agent in item.agents and item.component_id in registry
    ]


@app.command()
def doctor(
    probe_mcp: bool = typer.Option(True, "--probe-mcp/--no-probe-mcp"),
) -> None:
    """Diagnose every detected Agent without changing configuration."""
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    adapters = _adapter_map()
    state = StateStore()
    overall = True
    for installation in detected:
        if not installation.detected:
            continue
        console.print(f"[bold]{installation.agent.value.replace('_', ' ').title()}[/bold]")
        try:
            result = adapters[installation.agent].health_check(
                _state_components(state, installation.agent), probe_mcp=probe_mcp,
            )
        except Exception as exc:
            result = HealthCheckResult(checks=[])
            console.print(f"[red]FAIL[/red] health_check: {exc}")
            overall = False
        else:
            show_health(console, result)
            overall &= result.healthy
    console.print(f"\nOverall: {'PASS' if overall else 'WARNING'}")
    if not overall:
        raise typer.Exit(code=1)


@app.command("recommend")
def recommend_only(
    offline: bool = typer.Option(False, "--offline", help="Use Registry and verified cache only"),
) -> None:
    """Run the interview and print a Plan without installing."""
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    if not any(item.detected for item in detected):
        raise typer.Exit(code=1)
    try:
        plan, multi_plan, explanation = _build_plan(detected, _adapter_map(), offline=offline)
        show_plan(console, plan, multi_plan, explanation)
    except Exception as exc:
        _friendly_error(exc, "recommendation")
        raise typer.Exit(code=1) from exc


def _latest_manifest(root: Path) -> Path:
    candidates = sorted(root.glob("*/manifest.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no rollback manifests found in {root}")
    return candidates[0]


@app.command()
def rollback(
    path: Path | None = typer.Argument(None, help="Manifest file or transaction directory"),
    yes: bool = typer.Option(False, "--yes", help="Confirm rollback non-interactively"),
) -> None:
    """Restore the latest GrayOM transaction; existing user components are preserved."""
    try:
        manifest_path = path or _latest_manifest(grayom_home() / "backups")
        target = manifest_path / "manifest.json" if manifest_path.is_dir() else manifest_path
        raw = json.loads(target.read_text(encoding="utf-8"))
        agents = raw.get("selected_agents", ["codex"])
        console.print(f"Latest GrayOM Transaction\nDate: {raw.get('created_at', 'unknown')}\nAgents: {', '.join(agents)}")
        if not yes and not inquirer.confirm(message="Rollback this transaction?", default=False).execute():
            console.print("Cancelled. No changes were made.")
            return
        if "selected_agents" in raw:
            manifest = MultiAgentManifest.model_validate(raw)
            results = rollback_multi_agent(manifest, _adapter_map())
            errors = [error for result in results.values() for error in result.errors]
        else:
            manifest = InstallationManifest.model_validate(raw)
            result = CodexAdapter().rollback(manifest)
            errors = result.errors
        if errors:
            for error in errors:
                console.print(f"[red]- {error}[/red]")
            raise typer.Exit(code=1)
        console.print("[green]Rollback completed.[/green]")
    except typer.Exit:
        raise
    except Exception as exc:
        _friendly_error(exc, "rollback")
        raise typer.Exit(code=1) from exc


@app.command()
def update(
    yes: bool = typer.Option(False, "--yes", help="Approve all managed updates"),
) -> None:
    """Update only GrayOM-managed components whose verified source ref changed."""
    state = StateStore()
    plan = build_update_plan(state, load_registry())
    if not plan.items:
        console.print("[green]All GrayOM-managed components are up to date.[/green]")
        return
    for item in plan.items:
        console.print(f"[yellow]UPDATE[/yellow] {item.component.name}: {item.current_ref} -> {item.target_ref}")
        for finding in analyze_security([item.component]):
            console.print(f"  [{finding.level.value}] {finding.message}")
    if not yes and not inquirer.confirm(message="Install all updates?", default=False).execute():
        console.print("Cancelled. No changes were made.")
        return
    result = UpdateTransaction(_adapter_map(), grayom_home() / "backups").execute(plan)
    if not result.success:
        console.print(f"[red]Update failed: {result.error}[/red]")
        for error in result.rollback_errors:
            console.print(f"[red]- rollback: {error}[/red]")
        raise typer.Exit(code=1)
    for item in plan.items:
        managed = state.document.components[item.component.id]
        managed.source_ref = item.target_ref
        managed.updated_at = datetime.now(timezone.utc)
    state.save()
    console.print("[green]Update completed.[/green]")


@app.command("debug-info")
def debug_info() -> None:
    """Create a sanitized diagnostic bundle without credential values."""
    detected = detect_agents()
    state = StateStore()
    adapters = _adapter_map()
    health = {}
    for installation in detected:
        if installation.detected:
            try:
                result = adapters[installation.agent].health_check(
                    _state_components(state, installation.agent), probe_mcp=False,
                )
                health[installation.agent.value] = result.model_dump(mode="json")
            except Exception as exc:
                health[installation.agent.value] = {"error": str(exc)}
    recent_errors = []
    log_path = grayom_home() / "logs" / "grayom.jsonl"
    if log_path.exists():
        recent_errors = log_path.read_text(encoding="utf-8").splitlines()[-20:]
    info = redact({
        "grayom_version": __version__, "python_version": sys.version,
        "platform": detect_platform().model_dump(mode="json"),
        "agents": [item.model_dump(mode="json") for item in detected],
        "managed_components": list(state.document.components),
        "health": health, "recent_events": recent_errors,
    })
    target = grayom_home() / "debug" / f"debug-info-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(info, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    console.print(f"Sanitized debug info: {target}")


if __name__ == "__main__":
    app()
