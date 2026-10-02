"""Remove what GrayOM installed, and refuse to remove anything else.

`rollback` reverses the last transaction. It is not an uninstall: it cannot take away a
component installed three runs ago, and it works from a transaction manifest rather than from
what is on disk now. This module works from state, so a component can be removed long after
the run that installed it.

Three refusals carry the "safe" in safe uninstall, and each one is reported rather than
silently narrowing the work:

- a component that was already there before GrayOM is not GrayOM's to delete
- a component used by another Agent keeps its files; only the leaving Agent's registration goes
- a record written before GrayOM tracked what it wrote cannot be reversed exactly, so it is
  left alone instead of guessing which registration was ours
"""

from pathlib import Path

from pydantic import BaseModel, Field

from grayom_agent_guidance.adapters.base import AgentAdapter
from grayom_agent_guidance.models import (
    AgentType, ComponentRemovalResult, ComponentType, Ownership,
)
from grayom_agent_guidance.state import StateStore


SKIP_NOT_MANAGED = "installed before GrayOM, so it is not GrayOM's to remove"
SKIP_UNKNOWN_RECORD = (
    "this record predates the fields an exact removal needs, so GrayOM will not guess which "
    "registration was its own"
)
SKIP_NOT_INSTALLED = "not recorded as installed for this Agent"


class UninstallAction(BaseModel):
    """One component's removal, for one Agent, decided before anything is touched."""

    component_id: str
    name: str
    agent: AgentType
    component_type: ComponentType
    paths: list[Path] = Field(default_factory=list)
    mcp_names: list[str] = Field(default_factory=list)
    marketplaces: list[str] = Field(default_factory=list)
    keeps_files_for: list[AgentType] = Field(default_factory=list)


class UninstallPlan(BaseModel):
    actions: list[UninstallAction] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.actions

    def component_ids(self) -> list[str]:
        return list(dict.fromkeys(action.component_id for action in self.actions))


class UninstallResult(BaseModel):
    removals: list[ComponentRemovalResult] = Field(default_factory=list)
    forgotten: list[str] = Field(default_factory=list)
    retained: dict[str, list[AgentType]] = Field(default_factory=dict)

    @property
    def successful(self) -> bool:
        return all(item.successful for item in self.removals)

    @property
    def errors(self) -> list[str]:
        return [error for item in self.removals for error in item.errors]


def plan_uninstall(
    state: StateStore,
    component_ids: list[str] | None = None,
    agents: list[AgentType] | None = None,
) -> UninstallPlan:
    """Decide what would be removed, for which Agents, without touching anything."""
    plan = UninstallPlan()
    wanted = set(component_ids or state.document.components)
    for component_id in sorted(wanted):
        record = state.document.components.get(component_id)
        if record is None:
            plan.skipped[component_id] = "not managed by GrayOM"
            continue
        if record.ownership == Ownership.EXISTING:
            plan.skipped[component_id] = SKIP_NOT_MANAGED
            continue
        component = record.to_component()
        if component is None:
            plan.skipped[component_id] = SKIP_UNKNOWN_RECORD
            continue
        leaving = [agent for agent in record.agents if not agents or agent in agents]
        if not leaving:
            plan.skipped[component_id] = SKIP_NOT_INSTALLED
            continue
        staying = [agent for agent in record.agents if agent not in leaving]
        for agent in leaving:
            plan.actions.append(UninstallAction(
                component_id=component_id, name=component.name, agent=agent,
                component_type=component.type,
                # Files are shared between Agents through one install, so they only come out
                # once every Agent using them has left.
                paths=[] if staying else list(record.installation_paths),
                mcp_names=list(record.configured_mcp.get(agent, [])),
                marketplaces=list(record.added_marketplaces.get(agent, [])),
                keeps_files_for=staying,
            ))
    return plan


def apply_uninstall(
    plan: UninstallPlan,
    adapters: dict[AgentType, AgentAdapter],
    state: StateStore,
) -> UninstallResult:
    """Carry out a planned uninstall and bring state back in line with the disk.

    State is only updated for what actually came out. A removal that preserved a Skill the
    user had edited leaves that component recorded, so the next run still knows it is there.
    """
    result = UninstallResult()
    by_component: dict[str, list[UninstallAction]] = {}
    for action in plan.actions:
        by_component.setdefault(action.component_id, []).append(action)

    for component_id, actions in by_component.items():
        record = state.document.components.get(component_id)
        if record is None:
            continue
        component = record.to_component()
        if component is None:
            continue
        removed_for: list[AgentType] = []
        for action in actions:
            adapter = adapters.get(action.agent)
            if adapter is None:
                result.removals.append(ComponentRemovalResult(
                    component_id=component_id,
                    preserved=[f"{action.agent.value}: no adapter available"],
                ))
                continue
            removal = adapter.remove_component(
                component, action.paths, record.file_hashes,
                action.mcp_names, action.marketplaces,
            )
            result.removals.append(removal)
            if removal.successful and not _files_left_behind(removal):
                removed_for.append(action.agent)

        remaining = [agent for agent in record.agents if agent not in removed_for]
        if remaining:
            record.agents = remaining
            result.retained[component_id] = remaining
        elif removed_for:
            del state.document.components[component_id]
            result.forgotten.append(component_id)
    state.save()
    return result


def _files_left_behind(removal: ComponentRemovalResult) -> bool:
    """True when directories belonging to this Agent are still on disk.

    A Skill the user edited is preserved on purpose, and the component has to stay recorded
    for that Agent, or the next run would believe it is gone and install a second copy
    beside it. Only this Agent's own directories count: state keeps one path list for every
    Agent, and the other Agent's entries are not this one's to account for.
    """
    return removal.owned_paths > len(removal.removed_paths)
