from grayom_agent_guidance.adapters import AgentAdapter
from grayom_agent_guidance.models import (
    AgentComponentAction, AgentInstallation, AgentPlan, AgentType, CompatibilityStatus,
    Component, ComponentType, MultiAgentPlan, Ownership, RecommendationPlan,
    SharedComponentRecord, SkillSelectionPolicy,
)

from .compatibility import evaluate_compatibility
from .reconcile import reconcile_component
from .skill_selection import limit_for


def _with_skill_policy(
    component: Component, recommendation: RecommendationPlan, limit: int,
) -> Component:
    """Tell the adapter which Skills of a repository this run asked for.

    Discovery describes a repository; only the Plan knows what the person selected, so the
    policy is attached here rather than carried by the candidate.
    """
    if component.type != ComponentType.SKILL:
        return component
    scoped = component.model_copy(deep=True)
    scoped.skill_selection = SkillSelectionPolicy(
        capabilities=set(recommendation.capabilities), limit=limit,
    )
    return scoped


def build_multi_agent_plan(
    recommendation: RecommendationPlan,
    installations: dict[AgentType, AgentInstallation],
    adapters: dict[AgentType, AgentAdapter],
    skill_limit: int | None = None,
) -> MultiAgentPlan:
    limit = limit_for(recommendation.interview.mode, skill_limit)
    plans: dict[AgentType, AgentPlan] = {}
    for agent in recommendation.interview.agents:
        installation = installations[agent]
        adapter = adapters[agent]
        actions: list[AgentComponentAction] = []
        for item in recommendation.items:
            if not item.selected:
                continue
            component = _with_skill_policy(item.component, recommendation, limit)
            compatibility = evaluate_compatibility(component, installation)
            type_supported = {
                ComponentType.SKILL: adapter.capabilities.skills,
                ComponentType.MCP: adapter.capabilities.mcp,
                ComponentType.PLUGIN: adapter.capabilities.plugins,
            }[component.type]
            if not type_supported:
                compatibility.status = CompatibilityStatus.UNSUPPORTED
                compatibility.reason = (
                    f"{agent.value.replace('_', ' ').title()} adapter does not safely support "
                    f"{component.type.value} installation"
                )
            reconciliation = reconcile_component(
                agent, component, compatibility.status, adapter,
            )
            existing = reconciliation.status.value in {"UNCHANGED", "REFERENCE"}
            install = compatibility.status == CompatibilityStatus.SUPPORTED and not existing
            reason = reconciliation.reason if compatibility.status == CompatibilityStatus.SUPPORTED else compatibility.reason
            actions.append(AgentComponentAction(
                component=component, compatibility=compatibility, install=install,
                already_installed=existing, reason=reason, reconciliation=reconciliation.status,
            ))
        plans[agent] = AgentPlan(agent=agent, version=installation.version, actions=actions)

    shared: list[SharedComponentRecord] = []
    component_ids = {
        action.component.id
        for plan in plans.values() for action in plan.actions
        if action.component.type == ComponentType.MCP and (
            action.install or action.already_installed
        )
    }
    for component_id in sorted(component_ids):
        usages = [
            (agent, action) for agent, plan in plans.items() for action in plan.actions
            if action.component.id == component_id and action.component.type == ComponentType.MCP
            and (action.install or action.already_installed)
        ]
        users = [agent for agent, _ in usages]
        all_existing = all(action.already_installed for _, action in usages)
        shared.append(SharedComponentRecord(
            component_id=component_id,
            ownership=Ownership.EXISTING if all_existing else (
                Ownership.SHARED if len(users) > 1 else Ownership.GRAYOM_MODIFIED
            ),
            shared=len(users) > 1, used_by=users, prepared_count=1,
        ))
    return MultiAgentPlan(agents=plans, shared_components=shared)
