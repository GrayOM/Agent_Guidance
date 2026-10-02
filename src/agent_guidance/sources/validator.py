from agent_guidance.models import (
    AgentType, CandidateState, Component, ComponentType, InstallKind, MaintenanceStatus,
)


class ComponentValidator:
    def __init__(self, selected_agents: set[AgentType] | None = None) -> None:
        self.selected_agents = selected_agents or set()

    def validate(self, component: Component) -> Component:
        warnings = list(component.validation_warnings)
        hard_failures: list[str] = []
        evidence = {item.field: item.value for item in component.evidence}

        # A candidate stays eligible when it supports at least one selected Agent; per-Agent
        # applicability is recomputed later by compatibility evaluation and the install Plan.
        if self.selected_agents and not (self.selected_agents & component.supported_agents):
            hard_failures.append("no selected Agent is supported by this component")
        elif self.selected_agents and not self.selected_agents.issubset(component.supported_agents):
            unsupported = sorted(
                agent.value for agent in self.selected_agents - component.supported_agents
            )
            warnings.append("not applied to: " + ", ".join(unsupported))
        if not component.capabilities:
            hard_failures.append("no relevant capability could be verified")
        if not evidence.get("readme_present", True):
            warnings.append("README is missing or empty")
        if component.maintenance_metadata.archived:
            warnings.append("repository is archived")
        if component.maintenance_metadata.status == MaintenanceStatus.STALE:
            warnings.append("project appears stale")
        if not component.maintenance_metadata.license:
            warnings.append("license is missing or unclear")
        if component.install_method.kind == InstallKind.NONE:
            hard_failures.append("install method could not be determined")
        if component.type == ComponentType.PLUGIN:
            # A plugin is installable only through a marketplace: that is the path that
            # fetches it, validates its manifest and has an inverse to roll back.
            if component.install_method.kind != InstallKind.PLUGIN_MARKETPLACE:
                hard_failures.append(
                    "Plugin installation requires a marketplace plugin id; a Git URL alone "
                    "has no manifest to validate and no inverse to roll back"
                )
        for dependency in component.dependencies:
            if dependency.required and dependency.detected is False:
                warnings.append(f"{dependency.name} is required but was not detected")

        component.validation_warnings = list(dict.fromkeys(warnings + hard_failures))
        component.recommendable = not hard_failures
        component.candidate_state = CandidateState.VERIFIED if component.recommendable else CandidateState.REVIEW
        if component.recommendable and not component.trust.verified:
            component.trust.verified = True
            component.trust.verification_reason = (
                "repository metadata, README, structure, compatibility, and install method validated"
            )
        return component
