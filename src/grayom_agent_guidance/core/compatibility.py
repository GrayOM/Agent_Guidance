import re

from grayom_agent_guidance.models import (
    AgentInstallation, AgentType, CompatibilityResult, CompatibilityStatus, Component,
    ComponentType, InstallKind,
)


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)+", value)
    return tuple(int(part) for part in match.group(0).split(".")) if match else None


def evaluate_compatibility(
    component: Component, installation: AgentInstallation,
) -> CompatibilityResult:
    agent = installation.agent
    evidence = [
        f"{item.source}: {item.location or item.field}"
        for item in component.evidence if item.field in {"supported_agents", "type", "install_method"}
    ]
    if agent not in component.supported_agents:
        return CompatibilityResult(
            agent=agent, component_id=component.id, status=CompatibilityStatus.UNSUPPORTED,
            reason=f"{agent.value} is not listed in verified component support", evidence=evidence,
        )
    if not installation.detected:
        return CompatibilityResult(
            agent=agent, component_id=component.id, status=CompatibilityStatus.UNSUPPORTED,
            reason=f"{agent.value} is not installed", evidence=evidence,
        )
    if component.type == ComponentType.PLUGIN:
        if agent == AgentType.CODEX:
            return CompatibilityResult(
                agent=agent, component_id=component.id, status=CompatibilityStatus.UNSUPPORTED,
                reason="Codex Plugin installation is not supported by the current adapter", evidence=evidence,
            )
        if agent == AgentType.CLAUDE_CODE:
            return CompatibilityResult(
                agent=agent, component_id=component.id, status=CompatibilityStatus.PARTIAL,
                reason="Claude Code requires a verified marketplace identifier for persistent Plugin installation",
                evidence=evidence,
            )
        if agent == AgentType.CURSOR and component.install_method.kind != InstallKind.PLUGIN_GIT:
            return CompatibilityResult(
                agent=agent, component_id=component.id, status=CompatibilityStatus.PARTIAL,
                reason="Cursor Plugin requires a validated Git plugin manifest", evidence=evidence,
            )
    requirement = component.agent_requirements.get(agent)
    if requirement and requirement.min_version:
        current = _version_tuple(installation.version)
        minimum = _version_tuple(requirement.min_version)
        evidence.append(requirement.evidence or f"minimum version {requirement.min_version}")
        if current is None:
            return CompatibilityResult(
                agent=agent, component_id=component.id, status=CompatibilityStatus.UNKNOWN,
                reason=f"Unable to verify {agent.value} version compatibility", evidence=evidence,
            )
        if minimum and current < minimum:
            return CompatibilityResult(
                agent=agent, component_id=component.id, status=CompatibilityStatus.UNSUPPORTED,
                reason=f"requires {agent.value} >= {requirement.min_version}", evidence=evidence,
            )
    return CompatibilityResult(
        agent=agent, component_id=component.id, status=CompatibilityStatus.SUPPORTED,
        reason="component support and install method verified", evidence=evidence or [component.source],
    )
