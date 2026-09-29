from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from grayom_agent_guidance.models import RecommendationPlan


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


def show_plan(console: Console, plan: RecommendationPlan) -> None:
    table = Table(title="Recommended Agent Environment")
    table.add_column("Decision")
    table.add_column("Type")
    table.add_column("Component")
    table.add_column("Reason")
    for item in plan.items:
        table.add_row("Install" if item.selected else "Skipped", item.component.type.value, item.component.name, "; ".join(item.reasons))
    console.print(table)
    lines = [f"Overall Risk: {plan.overall_risk.value}"]
    lines.extend(f"- {finding.component_id}: {finding.message}" for finding in plan.security_findings)
    if plan.conflicts:
        lines.append("Conflicts:")
        lines.extend(f"- {finding.left_id} / {finding.right_id}: {finding.message}" for finding in plan.conflicts)
    console.print(Panel("\n".join(lines), title="Security & Conflicts"))

