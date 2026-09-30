from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grayom_agent_guidance.core.discovery import DiscoveryResult
from grayom_agent_guidance.models import (
    AgentInstallation, ComponentType, HealthCheckResult, MultiAgentPlan, RecommendationPlan,
)
from grayom_agent_guidance.core.explainer import PlanExplanation
from grayom_agent_guidance import __version__


LOGO = """
       ╭──────────╮
    ╭──╯   ╭──╮   ╰──╮
 ◀──╯      │◉ │      ╰──▶
    ╰──╮   ╰──╯   ╭──╯
       ╰──────────╯
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


def _eye_logo() -> Text:
    eye = Text(LOGO, style="bold bright_blue")
    eye.highlight_regex(r"╭──╮|│◉ │|╰──╯", style="bold bright_cyan")
    eye.highlight_regex("◉", style="bold bright_magenta")
    return eye


def show_header(console: Console) -> None:
    if console.size.width >= 78:
        layout = Table.grid(expand=True)
        layout.add_column(ratio=3, vertical="middle")
        layout.add_column(ratio=2, justify="center", vertical="middle")
        layout.add_row(_brand(), Align.center(_eye_logo(), vertical="middle"))
        content = layout
    else:
        content = Group(_brand(), Text(""), Align.center(_eye_logo()))
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


def show_plan(
    console: Console, plan: RecommendationPlan, multi_plan: MultiAgentPlan | None = None,
    explanation: PlanExplanation | None = None,
) -> None:
    table = Table(title="Recommended Agent Environment")
    table.add_column("Decision")
    table.add_column("Type")
    table.add_column("Component")
    table.add_column("Source")
    table.add_column("Maintenance")
    table.add_column("Reason")
    for item in plan.items:
        source = "Official" if item.component.trust.official else item.component.trust.source_type.value.title()
        table.add_row(
            "Install" if item.selected else "Skipped", item.component.type.value,
            item.component.name, source, item.component.maintenance_metadata.status.value.title(),
            "; ".join(item.reasons),
        )
    console.print(table)
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
    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    console.print(f"[green]✓[/green] {result.validated} unique candidates available\n")


def show_health(console: Console, result: HealthCheckResult) -> None:
    for check in result.checks:
        if check.passed:
            label = "[green]PASS[/green]"
        elif check.fatal:
            label = "[red]FAIL[/red]"
        else:
            label = "[yellow]WARN[/yellow]"
        console.print(f"{label} L{check.level.value} {check.name}: {check.message}")
