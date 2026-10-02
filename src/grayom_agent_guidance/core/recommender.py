from grayom_agent_guidance.models import (
    Component, ComponentType, InterviewAnswer, MaintenanceStatus, RecommendationItem,
    RecommendationPlan, SetupMode,
)

from .capability_inference import infer_capabilities


def _priority_key(component: Component, needed: set, mode: SetupMode) -> tuple:
    coverage = len(component.capabilities & needed)
    active = component.maintenance_metadata.status == MaintenanceStatus.ACTIVE
    stars = component.maintenance_metadata.stars or 0
    if mode == SetupMode.MINIMAL:
        return (
            -coverage,
            -int(component.trust.official),
            -int(component.trust.verified),
            -int(active),
            len(component.validation_warnings),
            component.context_cost,
            component.install_complexity,
            -component.quality_score,
            -stars,
            component.id,
        )
    return (
        -coverage,
        -int(component.trust.verified),
        -int(component.trust.official),
        -int(active),
        len(component.validation_warnings),
        -component.quality_score,
        component.install_complexity,
        component.context_cost,
        -stars,
        component.id,
    )


def _duplicate_of(candidate: Component, selected: list[Component], mode: SetupMode) -> Component | None:
    for chosen in selected:
        if candidate.type != chosen.type:
            continue
        if not (candidate.supported_agents & chosen.supported_agents):
            continue
        overlap = candidate.capabilities & chosen.capabilities
        union = candidate.capabilities | chosen.capabilities
        ratio = len(overlap) / len(union) if union else 0
        if candidate.type == ComponentType.MCP and (
            candidate.capabilities == chosen.capabilities
            or bool(candidate.tool_names & chosen.tool_names)
            or ratio >= 0.8
        ):
            return chosen
        if mode == SetupMode.MINIMAL and candidate.type == ComponentType.SKILL and ratio >= 0.75:
            return chosen
    return None


def recommend(answer: InterviewAnswer, candidates: list[Component]) -> RecommendationPlan:
    capabilities = infer_capabilities(answer)
    relevant = [item for item in candidates if item.capabilities & capabilities]
    relevant.sort(key=lambda item: _priority_key(item, capabilities, answer.mode))

    selected: list[Component] = []
    covered: set[tuple] = set()
    items: list[RecommendationItem] = []
    for candidate in relevant:
        eligible_agents = set(answer.agents) & candidate.supported_agents
        if not eligible_agents:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=["not supported by any selected Agent"],
            ))
            continue
        if not candidate.recommendable:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=candidate.validation_warnings or ["candidate requires manual review"],
            ))
            continue
        explicit_conflict = next((
            chosen for chosen in selected
            if (chosen.id in candidate.conflicts or candidate.id in chosen.conflicts)
            and bool(chosen.supported_agents & candidate.supported_agents)
        ), None)
        if explicit_conflict:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[f"conflicts with {explicit_conflict.name}"],
            ))
            continue
        explicit_overlap = next((
            chosen for chosen in selected
            if (chosen.id in candidate.overlaps or candidate.id in chosen.overlaps)
            and bool(chosen.supported_agents & candidate.supported_agents)
        ), None)
        if explicit_overlap and answer.mode == SetupMode.MINIMAL:
            overlap = candidate.capabilities & explicit_overlap.capabilities
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[
                    f"overlaps with {explicit_overlap.name} in "
                    + ", ".join(sorted(capability.value for capability in overlap))
                ],
            ))
            continue
        duplicate = _duplicate_of(candidate, selected, answer.mode)
        if duplicate:
            prefix = "Official implementation" if duplicate.trust.official else duplicate.name
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[f"duplicates MCP functionality; {prefix} provides the same capability"],
            ))
            continue

        candidate_pairs = {
            (agent, capability) for agent in eligible_agents
            for capability in candidate.capabilities & capabilities
        }
        new_coverage = candidate_pairs - covered
        overlap = candidate_pairs & covered
        choose = bool(new_coverage)
        if answer.mode == SetupMode.PERFORMANCE and not choose:
            choose = bool(overlap) and candidate.context_cost <= 4
        if choose:
            selected.append(candidate)
            covered.update(candidate_pairs)
            # Capabilities only, not one entry per Agent: the same capability repeated for
            # every Agent made the reason unreadable, and which Agents it applies to is
            # already the per-Agent table's job.
            reasons = ["covers: " + ", ".join(sorted(
                {capability.value for _, capability in new_coverage or overlap}
            ))]
            if candidate.trust.official:
                reasons.append("official implementation preferred")
            elif candidate.trust.verified:
                reasons.append("repository evidence validated")
        else:
            reasons = ["adds no capability beyond selected components"]
        items.append(RecommendationItem(component=candidate, selected=choose, reasons=reasons))

    handled = {item.component.id for item in items}
    for candidate in candidates:
        if candidate.id not in handled:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=["not relevant to inferred capabilities"],
            ))
    return RecommendationPlan(interview=answer, capabilities=capabilities, items=items)
