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
        ref = str(component.install_method.ref or "")
        if component.install_method.repository and len(ref) < 7:
            # `_install_ref` falls back to default_branch when the commit lookup did not land,
            # which is a deliberate fallback under an anonymous rate limit rather than a
            # defect, so this warns instead of refusing — dropping the candidate would shrink
            # the result set silently, which is the worse failure. A warning reaches the
            # approval screen, where "what gets installed is whatever this branch is at"
            # is something the user can weigh.
            warnings.append(
                f"not pinned to a commit: installs whatever '{ref or 'the default branch'}' "
                "points at when it is fetched"
            )
        if (
            component.install_method.kind == InstallKind.MCP_STDIO
            and component.install_method.from_readme
            and not component.install_method.package_version
        ):
            # The counterpart of the Plugin rule below, which MCP did not have. An npm server
            # whose launch command came from a README is installable only once the registry
            # has confirmed the package and given a version to pin to: `npx -y name` fetches
            # npm's current latest every time the Agent starts it, so an unpinned entry is not
            # the code that was reviewed on the approval screen. pin_failure carries why.
            hard_failures.append(
                component.install_method.pin_failure
                or "the npm package behind this MCP server could not be resolved to a version"
            )
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
