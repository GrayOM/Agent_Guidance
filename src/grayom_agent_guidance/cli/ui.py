from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grayom_agent_guidance.core.discovery import DiscoveryResult
from grayom_agent_guidance.models import (
    AgentInstallation, ComponentType, HealthCheckResult, MultiAgentManifest, MultiAgentPlan, RecommendationPlan,
)
from grayom_agent_guidance.core.explainer import PlanExplanation
from grayom_agent_guidance import __version__


# An eye around a reticle, echoing docs/assets/grayom-mark.svg. One line, because every
# multi-row attempt at this came out as scattered brackets once rendered at the width a
# 96-column terminal occupies, so the drawing stays in the SVG where curves are available.
#
# The pointer character U+276F must not appear here. scripts/capture_screens.py treats a line
# starting with it as a question waiting for an answer, so a header carrying one would have the
# capture typing into the startup banner.
LOGO = """
   ( ◎ )
"""


def _brand() -> Group:
    name = Text.assemble(
        ("Gray", "bold bright_cyan"),
        ("OM", "bold bright_magenta"),
    )
    name.stylize("bold", 0, len(name))
    return Group(
        Text("WELCOME TO", style="bold white"),
        Text(""),
        name,
        Text("AGENT GUIDANCE", style="bold white"),
        Text("AI Agent Environment Manager", style="dim"),
    )


def _mark() -> Text:
    mark = Text(LOGO, style="bold bright_blue")
    mark.highlight_regex("◎", style="bold bright_cyan")
    return mark


def show_header(console: Console) -> None:
    if console.size.width >= 78:
        layout = Table.grid(expand=True)
        layout.add_column(ratio=3, vertical="middle")
        layout.add_column(ratio=2, justify="center", vertical="middle")
        layout.add_row(_brand(), Align.center(_mark(), vertical="middle"))
        content = layout
    else:
        content = Group(_brand(), Text(""), Align.center(_mark()))
    console.print(
        Panel(
            content,
            border_style="bright_blue",
            padding=(1, 2),
            subtitle=f"v{__version__}",
            subtitle_align="right",
        )
    )
    console.print()


def show_detected_agents(console: Console, agents: list[AgentInstallation]) -> None:
    console.print("[bold]Detected Agents:[/bold]")
    for item in agents:
        mark = "[green]✓[/green]" if item.detected else "[dim]✗[/dim]"
        suffix = f" ({item.version})" if item.version else ""
        console.print(f"{mark} {item.agent.value.replace('_', ' ').title()}{suffix}")
    console.print()


def _show_not_selected(console: Console, plan: RecommendationPlan) -> None:
    """The candidates that were considered and passed over, counted by reason."""
    counts: dict[str, int] = {}
    for item in plan.items:
        if item.selected:
            continue
        reason = item.reasons[0] if item.reasons else "not selected"
        counts[reason] = counts.get(reason, 0) + 1
    if not counts:
        return
    total = sum(counts.values())
    detail = "; ".join(
        f"{count} {reason}" for reason, count in sorted(counts.items(), key=lambda row: -row[1])
    )
    console.print(f"[dim]{total} other candidates considered: {detail}[/dim]")


def show_plan(
    console: Console, plan: RecommendationPlan, multi_plan: MultiAgentPlan | None = None,
    explanation: PlanExplanation | None = None,
) -> None:
    # Only what will be installed gets a row. Every candidate discovery considered used to
    # get one, so a live run put ten "Skipped" rows around the two that mattered.
    table = Table(title="Recommended Agent Environment")
    table.add_column("Type")
    table.add_column("Component")
    table.add_column("Source")
    table.add_column("Maintenance")
    table.add_column("Reason")
    for item in plan.items:
        if not item.selected:
            continue
        source = "Official" if item.component.trust.official else item.component.trust.source_type.value.title()
        table.add_row(
            item.component.type.value, item.component.name, source,
            item.component.maintenance_metadata.status.value.title(), "; ".join(item.reasons),
        )
    console.print(table)
    _show_not_selected(console, plan)
    if explanation:
        console.print("\n[bold]Why this setup?[/bold]")
        for line in explanation.summary:
            console.print(f"- {line}")
        explanation_map = {item.component_id: item for item in explanation.components}
        for component in plan.selected:
            detail = explanation_map.get(component.id)
            if detail:
                console.print(f"[bold]{component.name}[/bold]")
                for line in detail.reasons + detail.why_selected:
                    console.print(f"  - {line}")
    if multi_plan:
        shared = [item for item in multi_plan.shared_components if item.shared]
        if shared:
            console.print("\n[bold]Shared Components[/bold]")
            for item in shared:
                console.print(
                    f"- {item.component_id}: prepare once; references for "
                    + ", ".join(agent.value for agent in item.used_by)
                )
        for agent, agent_plan in multi_plan.agents.items():
            agent_table = Table(title=agent.value.replace("_", " ").title())
            agent_table.add_column("Change")
            agent_table.add_column("Component")
            agent_table.add_column("Compatibility")
            agent_table.add_column("Reason")
            for action in agent_plan.actions:
                agent_table.add_row(
                    action.reconciliation.value, action.component.name,
                    action.compatibility.status.value, action.reason,
                )
            console.print(agent_table)
    counts = {
        kind: sum(1 for component in plan.selected if component.type == kind)
        for kind in ComponentType
    }
    lines = [
        f"Agent: {', '.join(agent.value for agent in plan.interview.agents)}",
        f"Mode: {plan.interview.mode.value.title()}",
        f"Overall Risk: {plan.overall_risk.value}",
    ]
    lines.extend(
        f"- [{finding.level.value}] {finding.component_id}: {finding.message}"
        for finding in plan.security_findings
    )
    if plan.uncovered_capabilities:
        lines.append("Uncovered capabilities:")
        lines.extend(f"- {item.value}" for item in sorted(plan.uncovered_capabilities, key=lambda value: value.value))
    if plan.conflicts:
        lines.append("Conflicts:")
        lines.extend(f"- {finding.left_id} / {finding.right_id}: {finding.message}" for finding in plan.conflicts)
    lines.extend([
        "Changes:",
        f"- {counts[ComponentType.SKILL]} Skills will be installed",
        f"- {counts[ComponentType.MCP]} MCP servers will be configured",
        f"- {counts[ComponentType.PLUGIN]} Plugins will be installed",
        "- Every selected Agent config will be backed up and merged",
    ])
    console.print(Panel("\n".join(lines), title="Security & Conflicts"))


def show_discovery(console: Console, result: DiscoveryResult) -> None:
    console.print("[bold]Component discovery:[/bold]")
    for source in result.sources:
        mark = "[green]✓[/green]" if source.checked else "[yellow]![/yellow]"
        console.print(
            f"{mark} {source.source.title()}: {source.discovered} discovered, "
            f"{source.validated} validated"
        )
        if source.rate_limit_remaining is not None:
            console.print(f"  GitHub rate limit remaining: {source.rate_limit_remaining}")
    # Sources fail for the same reason at the same time, so the same sentence arrives twice.
    for warning in dict.fromkeys(result.warnings):
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    console.print(f"[green]✓[/green] {result.validated} unique candidates available\n")


def show_installed(console: Console, manifest: MultiAgentManifest) -> None:
    """One line per component, then what was deliberately left out.

    A Skill repository can hold dozens of Skills, so the user has to be told what landed
    without reading their Agent's context to find out. Lines are grouped by component
    rather than by Agent: the same component installed for two Agents is one thing that
    happened, and counting its Skills once per Agent would double every number.
    """
    if not manifest.outcomes:
        return
    grouped: dict[str, list] = {}
    for outcome in manifest.outcomes:
        grouped.setdefault(outcome.component_id, []).append(outcome)

    console.print("\n[bold]Installed[/bold]")
    skipped: dict[str, int] = {}
    for outcomes in grouped.values():
        first = outcomes[0]
        agents = ", ".join(item.agent.value.replace("_", " ").title() for item in outcomes)
        console.print(f"  [green]+[/green] {first.name} — {first.summary()} [dim]({agents})[/dim]")
        for reason, count in first.skills_skipped.items():
            skipped[reason] = skipped.get(reason, 0) + count
    if skipped:
        detail = ", ".join(
            f"{count} {reason}" for reason, count in sorted(skipped.items(), key=lambda x: -x[1])
        )
        console.print(f"  [dim]Skills left out: {detail}[/dim]")


def show_health(console: Console, result: HealthCheckResult) -> None:
    for check in result.checks:
        if check.passed:
            label = "[green]PASS[/green]"
        elif check.fatal:
            label = "[red]FAIL[/red]"
        else:
            label = "[yellow]WARN[/yellow]"
        console.print(f"{label} L{check.level.value} {check.name}: {check.message}")


def show_uninstall_plan(console: Console, plan) -> None:
    """What will be taken away, and what will deliberately stay, before anything is touched."""
    if plan.actions:
        table = Table(title="Uninstall Plan")
        table.add_column("Component")
        table.add_column("Type")
        table.add_column("Agent")
        table.add_column("What goes")
        for action in plan.actions:
            goes = []
            if action.paths:
                goes.append(f"{len(action.paths)} Skill directories")
            if action.mcp_names:
                goes.append("MCP " + ", ".join(action.mcp_names))
            if action.marketplaces:
                goes.append("marketplace " + ", ".join(action.marketplaces))
            if action.keeps_files_for:
                kept = ", ".join(item.value.replace("_", " ").title() for item in action.keeps_files_for)
                goes.append(f"registration only — files stay for {kept}")
            table.add_row(
                action.name, action.component_type.value,
                action.agent.value.replace("_", " ").title(),
                "; ".join(goes) or "nothing recorded",
            )
        console.print(table)
    for component_id, reason in plan.skipped.items():
        console.print(f"  [dim]- {component_id}: {reason}[/dim]")


def show_uninstall_result(console: Console, result) -> None:
    console.print("\n[bold]Removed[/bold]")
    for removal in result.removals:
        parts = []
        if removal.removed_paths:
            parts.append(f"{len(removal.removed_paths)} Skill directories")
        if removal.removed_mcp:
            parts.append("MCP " + ", ".join(removal.removed_mcp))
        if removal.removed_plugins:
            parts.append("plugin " + ", ".join(removal.removed_plugins))
        if removal.removed_marketplaces:
            parts.append("marketplace " + ", ".join(removal.removed_marketplaces))
        if parts:
            console.print(f"  [green]-[/green] {removal.component_id} — {'; '.join(parts)}")
        for note in removal.preserved:
            console.print(f"  [yellow]![/yellow] {removal.component_id} kept — {note}")
        for error in removal.errors:
            console.print(f"  [red]x[/red] {removal.component_id} — {error}")
    for component_id, agents in result.retained.items():
        names = ", ".join(item.value.replace("_", " ").title() for item in agents)
        console.print(f"  [dim]{component_id} is still installed for {names}[/dim]")
