from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from grayom_agent_guidance.core.discovery import DiscoveryResult
from grayom_agent_guidance.models import AgentInstallation, ComponentType, HealthCheckResult, RecommendationPlan


LOGO = r"""
   ____                 ____  __  __
  / ___|_ __ __ _ _   _/ __ \|  \/  |
 | |  _| '__/ _` | | | | |  | | |\/| |
 | |_| | | | (_| | |_| | |__| | |  | |
  \____|_|  \__,_|\__, |\____/|_|  |_|
                  |___/
"""


def show_header(console: Console) -> None:
    console.print(LOGO, style="bold bright_black")
    console.print("[bold]GrayOM Agent Guidance[/bold]\nAI Agent Environment Manager\n")


def show_detected_agents(console: Console, agents: list[AgentInstallation]) -> None:
    console.print("[bold]Detected Agents:[/bold]")
    for item in agents:
        mark = "[green]✓[/green]" if item.detected else "[dim]✗[/dim]"
        suffix = f" ({item.version})" if item.version else ""
        console.print(f"{mark} {item.agent.value.replace('_', ' ').title()}{suffix}")
    console.print()


def show_plan(console: Console, plan: RecommendationPlan) -> None:
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
    counts = {
        kind: sum(1 for component in plan.selected if component.type == kind)
        for kind in ComponentType
    }
    lines = [
        f"Agent: {', '.join(agent.value for agent in plan.interview.agents)}",
        f"Mode: {plan.interview.mode.value.title()}",
        f"Overall Risk: {plan.overall_risk.value}",
    ]
    lines.extend(f"- {finding.component_id}: {finding.message}" for finding in plan.security_findings)
    if plan.conflicts:
        lines.append("Conflicts:")
        lines.extend(f"- {finding.left_id} / {finding.right_id}: {finding.message}" for finding in plan.conflicts)
    lines.extend([
        "Changes:",
        f"- {counts[ComponentType.SKILL]} Skills will be installed",
        f"- {counts[ComponentType.MCP]} MCP servers will be configured",
        f"- {counts[ComponentType.PLUGIN]} Plugins will be installed",
        "- Existing Codex config will be backed up and merged",
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
        console.print(f"{label} {check.name}: {check.message}")
