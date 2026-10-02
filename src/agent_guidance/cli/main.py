import json
import sys
from enum import IntEnum
from datetime import datetime, timezone
from pathlib import Path

import typer
from InquirerPy import inquirer
from rich.console import Console

from agent_guidance import __version__
from agent_guidance.adapters import (
    AgentAdapter, ClaudeCodeAdapter, CodexAdapter, detect_agents,
)
from agent_guidance.config import agent_guidance_home, load_config
from agent_guidance.core import (
    MultiAgentInstallationTransaction, UpdateTransaction, analyze_conflicts,
    analyze_security, build_multi_agent_plan, build_update_plan, detect_platform,
    discover_components_sync, explain_plan, find_incomplete_transactions, recommend, rollback_multi_agent,
)
from agent_guidance.errors import AgentGuidanceError
from agent_guidance.models import (
    AgentInstallation, AgentType, Component, HealthCheckResult, InstallationManifest,
    MultiAgentManifest, Ownership,
)
from agent_guidance.core.uninstall import apply_uninstall, plan_uninstall
from agent_guidance.sources.upstream import resolve_upstream_refs
from agent_guidance.observability import EventLogger, redact
from agent_guidance.registry import load_registry
from agent_guidance.schema import load_versioned_json
from agent_guidance.state import StateStore
from agent_guidance.runtime import OperationLock

from .interview import run_interview
from .ui import (
    show_detected_agents, show_discovery, show_header, show_health, show_installed, show_plan,
    show_uninstall_plan, show_uninstall_result,
)

# Two panels rather than one flat list of seven commands. Someone opening --help for the
# first time needs to see that there is one command to run and that the rest only matter when
# something is wrong; a single list made every command look equally necessary.
EVERYDAY = "Everyday use"
TROUBLE = "When something goes wrong"

app = typer.Typer(
    no_args_is_help=False,
    help=(
        "Set up Codex and Claude Code extensions for the work you actually do.\n\n"
        "Run 'agent-guidance' with no command and follow the menu. Nothing is written to your Agent "
        "configuration until you approve the plan it shows you."
    ),
)
console = Console()
_verbose = False


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    CANCELLED = 2
    CONFIGURATION = 3
    INSTALLATION = 4
    HEALTH = 5
    ROLLBACK = 6


def _adapter_map(home: Path | None = None) -> dict[AgentType, AgentAdapter]:
    return {
        AgentType.CODEX: CodexAdapter(home),
        AgentType.CLAUDE_CODE: ClaudeCodeAdapter(home),
    }


def _friendly_error(exc: Exception, operation: str) -> None:
    if isinstance(exc, AgentGuidanceError):
        message, reason, action = exc.user_message, exc.technical_message, exc.suggested_action
    else:
        message = f"Agent Guidance could not complete {operation}."
        reason = str(exc)
        action = "Run: agent-guidance doctor"
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
    multi_plan = build_multi_agent_plan(
        plan, installation_map, adapters,
        skill_limit=load_config().skills.max_per_component,
    )
    return plan, multi_plan, explain_plan(plan)


def _run_setup(probe_mcp: bool = True, offline: bool = False, dry_run: bool = False) -> None:
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    if not any(item.detected for item in detected):
        console.print("[red]No supported Agent was detected. Agent Guidance does not install Agent applications.[/red]")
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
            raise typer.Exit(code=ExitCode.CANCELLED)
        logger = EventLogger(verbose=_verbose)
        selected_adapters = {agent: adapters[agent] for agent in multi_plan.agents}
        with OperationLock(agent_guidance_home() / "agent-guidance.lock", "setup"):
            incomplete = find_incomplete_transactions(agent_guidance_home() / "backups")
            for prior in incomplete:
                console.print(
                    f"[yellow]! WARNING[/yellow] Incomplete transaction {prior.transaction_id} "
                    f"({prior.state.value}) detected; restoring it before setup."
                )
                recovery = rollback_multi_agent(prior, adapters)
                recovery_errors = [error for item in recovery.values() for error in item.errors]
                if recovery_errors:
                    raise RuntimeError("incomplete transaction recovery failed: " + "; ".join(recovery_errors))
            try:
                result = MultiAgentInstallationTransaction(
                    selected_adapters, agent_guidance_home() / "backups",
                ).execute(multi_plan, probe_mcp=probe_mcp)
            except KeyboardInterrupt:
                console.print("\nOperation interrupted. Agent Guidance stopped before reporting success.")
                raise typer.Exit(code=ExitCode.INSTALLATION)
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
            raise typer.Exit(code=ExitCode.INSTALLATION)
        StateStore().record(multi_plan, result.manifest)
        console.print("\n[bold green]Installation completed.[/bold green]")
        show_installed(console, result.manifest)
        for warning in result.manifest.shared_warnings:
            console.print(f"[yellow]! WARNING[/yellow] {warning}")
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
    if not sys.stdin.isatty():
        console.print("Interactive mode requires a TTY. Use a direct command such as 'agent-guidance doctor'.")
        raise typer.Exit(code=ExitCode.CONFIGURATION)
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    # Every command has an entry here, so the menu is a complete way to use Agent Guidance and not a
    # shortcut to some of it. 'uninstall' was missing: it existed only as a typed command, which
    # left the menu unable to undo what the menu had just done. Each line says what happens,
    # because "Setup Agent Environment" does not tell a first-time user whether it writes files.
    action = inquirer.select(message="What would you like to do?", choices=[
        {"name": "Set up my Agents  -  choose my work, review the plan, then install",
         "value": "setup"},
        {"name": "Just show me the plan  -  decide nothing, install nothing", "value": "recommend"},
        {"name": "Check for updates  -  see if anything installed has a newer version",
         "value": "update"},
        {"name": "Check my setup  -  confirm the Agents and everything installed still work",
         "value": "doctor"},
        {"name": "Remove what Agent Guidance installed  -  your own files stay", "value": "uninstall"},
        {"name": "Undo the last change  -  restore the most recent backup", "value": "rollback"},
        {"name": "Exit", "value": "exit"},
    ]).execute()
    if action == "setup":
        _run_setup()
    elif action == "recommend":
        recommend_only(offline=False)
    elif action == "doctor":
        doctor(probe_mcp=True)
    elif action == "update":
        update(yes=False)
    elif action == "uninstall":
        # --all, because the menu has no way to name one component, and dry_run is False so the
        # confirmation inside uninstall is the one place the user decides. Empty lists rather
        # than None: uninstall tests both for truth, and None contradicts its annotation.
        uninstall(components=[], agent=[], remove_all=True, yes=False, dry_run=False)
    elif action == "rollback":
        rollback(path=None, yes=False)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit", is_eager=True),
    verbose: bool = typer.Option(False, "--verbose", help="Show technical error details"),
) -> None:
    """Open the interactive menu when no direct command is supplied."""
    global _verbose
    if version:
        console.print(f"Agent Guidance {__version__}")
        raise typer.Exit()
    _verbose = verbose or load_config().ui.verbose
    if ctx.invoked_subcommand is None:
        _interactive_menu()


@app.command(rich_help_panel=EVERYDAY)
def setup(
    offline: bool = typer.Option(
        False, "--offline", help="Skip GitHub and use only the built-in list and verified cache"
    ),
    # Internal: the health check probes MCP servers by starting them, which a test or a CI run
    # needs to switch off. Hidden because turning it off makes the result weaker, and no user
    # has a reason to want that.
    probe_mcp: bool = typer.Option(True, "--probe-mcp/--no-probe-mcp", hidden=True),
    # Hidden because 'agent-guidance recommend' is the same preview under a name that says so. Kept
    # because scripts/real_agent_check.py and the test suite drive setup itself.
    dry_run: bool = typer.Option(False, "--dry-run", hidden=True),
) -> None:
    """Choose your work, review the plan, then install (asks before changing anything)."""
    _run_setup(probe_mcp=probe_mcp, offline=offline, dry_run=dry_run)


def _state_components(state: StateStore, agent: AgentType) -> list[Component]:
    """Components Agent Guidance installed for this Agent, as installed.

    State is preferred over the Registry because it records the component that was actually
    applied; the Registry is only a fallback for records written before state carried the
    type and install method, and it never contains a component discovered on GitHub.
    """
    registry = {component.id: component for component in load_registry()}
    components = []
    for item in state.document.components.values():
        if agent not in item.agents:
            continue
        restored = item.to_component() or registry.get(item.component_id)
        if restored:
            components.append(restored)
    return components


@app.command(rich_help_panel=TROUBLE)
def doctor(
    probe_mcp: bool = typer.Option(True, "--probe-mcp/--no-probe-mcp", hidden=True),
) -> None:
    """Check whether your Agents and everything Agent Guidance installed still work."""
    show_header(console)
    detected = detect_agents()
    show_detected_agents(console, detected)
    adapters = _adapter_map()
    state = StateStore()
    for warning in state.warnings:
        console.print(f"[yellow]! WARNING[/yellow] {warning}")
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


@app.command("recommend", rich_help_panel=EVERYDAY)
def recommend_only(
    offline: bool = typer.Option(
        False, "--offline", help="Skip GitHub and use only the built-in list and verified cache"
    ),
) -> None:
    """Show what Agent Guidance would install, and why, without installing it."""
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


@app.command(rich_help_panel=TROUBLE)
def rollback(
    path: Path | None = typer.Argument(
        None, help="An older backup to restore; the newest one is used when omitted"
    ),
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation"),
) -> None:
    """Undo the last change Agent Guidance made. Anything you installed yourself is left alone."""
    try:
        manifest_path = path or _latest_manifest(agent_guidance_home() / "backups")
        target = manifest_path / "manifest.json" if manifest_path.is_dir() else manifest_path
        raw = load_versioned_json(target)
        agents = raw.get("selected_agents", ["codex"])
        console.print(f"Latest Agent Guidance Transaction\nDate: {raw.get('created_at', 'unknown')}\nAgents: {', '.join(agents)}")
        if not yes and not inquirer.confirm(message="Rollback this transaction?", default=False).execute():
            console.print("Cancelled. No changes were made.")
            raise typer.Exit(code=ExitCode.CANCELLED)
        with OperationLock(agent_guidance_home() / "agent-guidance.lock", "rollback"):
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
            raise typer.Exit(code=ExitCode.ROLLBACK)
        console.print("[green]Rollback completed.[/green]")
    except typer.Exit:
        raise
    except Exception as exc:
        _friendly_error(exc, "rollback")
        raise typer.Exit(code=1) from exc


@app.command(rich_help_panel=TROUBLE)
def uninstall(
    components: list[str] = typer.Argument(
        None, help="What to remove, by name; use --all for everything Agent Guidance installed",
    ),
    agent: list[str] = typer.Option(
        None, "--agent", help="Remove from one Agent only, leaving the other as it is",
    ),
    remove_all: bool = typer.Option(False, "--all", help="Remove everything Agent Guidance installed"),
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed, remove nothing"),
) -> None:
    """Remove what Agent Guidance installed. Your own files, and any you edited, stay."""
    show_header(console)
    state = StateStore()
    for warning in state.warnings:
        console.print(f"[yellow]! WARNING[/yellow] {warning}")
    if not components and not remove_all:
        console.print(
            "Name the components to remove, or pass --all. "
            "'agent-guidance debug-info' lists what Agent Guidance installed."
        )
        raise typer.Exit(code=ExitCode.CANCELLED)
    try:
        agents = [AgentType(value) for value in agent] if agent else None
    except ValueError as exc:
        console.print(f"[red]Unknown Agent: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    try:
        plan = plan_uninstall(state, list(components) if components else None, agents)
        show_uninstall_plan(console, plan)
        if plan.empty:
            console.print("[green]Nothing to remove.[/green]")
            return
        if dry_run:
            console.print("\n[bold yellow]DRY RUN[/bold yellow]\nNothing was removed.")
            return
        if not yes and not inquirer.confirm(
            message="Remove these components?", default=False,
        ).execute():
            console.print("Cancelled. Nothing was removed.")
            raise typer.Exit(code=ExitCode.CANCELLED)
        logger = EventLogger(verbose=_verbose)
        with OperationLock(agent_guidance_home() / "agent-guidance.lock", "uninstall"):
            result = apply_uninstall(plan, _adapter_map(), state)
        show_uninstall_result(console, result)
        logger.write(
            "uninstall_complete", components=plan.component_ids(),
            result="success" if result.successful else "failed", error="; ".join(result.errors),
        )
        if not result.successful:
            raise typer.Exit(code=ExitCode.INSTALLATION)
    except typer.Exit:
        raise
    except Exception as exc:
        _friendly_error(exc, "uninstall")
        raise typer.Exit(code=1) from exc


@app.command(rich_help_panel=EVERYDAY)
def update(
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation"),
    offline: bool = typer.Option(
        False, "--offline", help="Skip GitHub and compare against the built-in list only"
    ),
) -> None:
    """Check whether anything Agent Guidance installed has a newer version, and offer to update it."""
    state = StateStore()
    for warning in state.warnings:
        console.print(f"[yellow]! WARNING[/yellow] {warning}")
    managed = [
        item for item in state.document.components.values()
        if item.ownership != Ownership.EXISTING
    ]
    upstream = {}
    if managed and not offline:
        with console.status("Checking upstream references..."):
            upstream = resolve_upstream_refs(managed)
        unchecked = [item for item in upstream.values() if not item.checked]
        if not upstream:
            console.print(
                "[yellow]! WARNING[/yellow] Upstream could not be reached; "
                "comparing against the Local Registry instead."
            )
        for item in unchecked:
            console.print(f"[yellow]! WARNING[/yellow] {item.component_id}: {item.reason}")
    plan = build_update_plan(state, load_registry(), upstream=upstream)
    if not plan.items:
        console.print("[green]All Agent Guidance-managed components are up to date.[/green]")
        return
    for item in plan.items:
        console.print(
            f"[yellow]UPDATE[/yellow] {item.component.name}: {item.current_ref} -> "
            f"{item.target_ref} ({item.reason})"
        )
        for warning in item.warnings:
            console.print(f"  [yellow]! WARNING[/yellow] {warning}")
        for finding in analyze_security([item.component]):
            console.print(f"  [{finding.level.value}] {finding.message}")
    if not yes and not inquirer.confirm(message="Install all updates?", default=False).execute():
        console.print("Cancelled. No changes were made.")
        raise typer.Exit(code=ExitCode.CANCELLED)
    with OperationLock(agent_guidance_home() / "agent-guidance.lock", "update"):
        result = UpdateTransaction(_adapter_map(), agent_guidance_home() / "backups").execute(plan)
    if not result.success:
        console.print(f"[red]Update failed: {result.error}[/red]")
        for error in result.rollback_errors:
            console.print(f"[red]- rollback: {error}[/red]")
        raise typer.Exit(code=ExitCode.INSTALLATION)
    for item in plan.items:
        managed = state.document.components[item.component.id]
        managed.source_ref = item.target_ref
        managed.updated_at = datetime.now(timezone.utc)
        state.refresh_hashes(item.component.id)
    state.save()
    console.print("[green]Update completed.[/green]")


@app.command("debug-info", rich_help_panel=TROUBLE)
def debug_info() -> None:
    """Write a report you can attach to a bug report. No tokens or passwords are included."""
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
    log_path = agent_guidance_home() / "logs" / "agent-guidance.jsonl"
    if log_path.exists():
        recent_errors = log_path.read_text(encoding="utf-8").splitlines()[-20:]
    info = redact({
        "agent_guidance_version": __version__, "python_version": sys.version,
        "platform": detect_platform().model_dump(mode="json"),
        "agents": [item.model_dump(mode="json") for item in detected],
        "managed_components": list(state.document.components),
        "health": health, "recent_events": recent_errors,
    })
    target = agent_guidance_home() / "debug" / f"debug-info-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(info, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    console.print(f"Sanitized debug info: {target}")


if __name__ == "__main__":
    app()
