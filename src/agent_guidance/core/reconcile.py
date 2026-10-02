from agent_guidance.adapters import AgentAdapter
from agent_guidance.adapters.codex import MCP_DIFFERENT_SETTINGS_REASON
from agent_guidance.models import (
    AgentType, CompatibilityStatus, Component, ComponentType, ReconciliationItem,
    ReconciliationStatus,
)


def reconcile_component(
    agent: AgentType, component: Component, compatibility_status: CompatibilityStatus,
    adapter: AgentAdapter,
) -> ReconciliationItem:
    if compatibility_status != CompatibilityStatus.SUPPORTED:
        return ReconciliationItem(
            agent=agent, component_id=component.id, status=ReconciliationStatus.SKIP,
            reason=f"compatibility is {compatibility_status.value}",
        )
    status_method = getattr(adapter, "existing_component_status", None)
    existing, reason = status_method(component) if status_method else (False, None)
    if existing and reason == MCP_DIFFERENT_SETTINGS_REASON:
        return ReconciliationItem(
            agent=agent, component_id=component.id, status=ReconciliationStatus.CONFLICT,
            reason=reason,
        )
    if existing:
        status = ReconciliationStatus.REFERENCE if component.type == ComponentType.MCP else ReconciliationStatus.UNCHANGED
        return ReconciliationItem(
            agent=agent, component_id=component.id, status=status,
            reason=reason or "compatible component already exists",
        )
    return ReconciliationItem(
        agent=agent, component_id=component.id, status=ReconciliationStatus.ADD,
        reason="component is not present",
    )
