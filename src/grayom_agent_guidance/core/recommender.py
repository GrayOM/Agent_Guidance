from grayom_agent_guidance.models import (
    Component, InterviewAnswer, RecommendationItem, RecommendationPlan, SetupMode,
)

from .capability_inference import infer_capabilities


def recommend(answer: InterviewAnswer, candidates: list[Component]) -> RecommendationPlan:
    capabilities = infer_capabilities(answer)
    relevant = [item for item in candidates if item.capabilities & capabilities]
    relevant.sort(
        key=lambda item: (
            len(item.capabilities & capabilities) * 20 + item.quality_score
            - (item.context_cost * (12 if answer.mode == SetupMode.MINIMAL else 3))
            + (10 if item.official else 0)
        ),
        reverse=True,
    )

    selected: list[Component] = []
    covered = set()
    items: list[RecommendationItem] = []
    for candidate in relevant:
        if not set(answer.agents).issubset(candidate.supported_agents):
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=["not supported by every selected Agent"],
            ))
            continue
        new_coverage = (candidate.capabilities & capabilities) - covered
        overlaps = candidate.capabilities & covered
        explicit_conflict = next((
            chosen for chosen in selected
            if chosen.id in candidate.conflicts or candidate.id in chosen.conflicts
        ), None)
        explicit_overlap = next((
            chosen for chosen in selected
            if chosen.id in candidate.overlaps or candidate.id in chosen.overlaps
        ), None)
        duplicate_mcp = next((
            chosen for chosen in selected
            if candidate.type.value == "mcp" and chosen.type.value == "mcp"
            and (
                candidate.capabilities == chosen.capabilities
                or bool(candidate.tool_names & chosen.tool_names)
            )
        ), None)
        if duplicate_mcp:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[f"duplicates MCP functionality provided by {duplicate_mcp.name}"],
            ))
            continue
        if explicit_conflict:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[f"conflicts with {explicit_conflict.name}"],
            ))
            continue
        if explicit_overlap and answer.mode == SetupMode.MINIMAL:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=[
                    f"overlaps with {explicit_overlap.name} in "
                    + ", ".join(sorted(c.value for c in candidate.capabilities & explicit_overlap.capabilities))
                ],
            ))
            continue
        choose = bool(new_coverage) or (
            answer.mode == SetupMode.PERFORMANCE
            and bool(candidate.capabilities & capabilities)
            and candidate.context_cost <= 3
        )
        if answer.mode == SetupMode.MINIMAL and not new_coverage:
            choose = False
        reasons = []
        if choose:
            selected.append(candidate)
            covered.update(candidate.capabilities)
            reasons.append("covers: " + ", ".join(sorted(c.value for c in new_coverage or overlaps)))
        else:
            reasons.append("adds no capability beyond selected components")
        items.append(RecommendationItem(component=candidate, selected=choose, reasons=reasons))

    known_ids = {item.component.id for item in items}
    for candidate in candidates:
        if candidate.id not in known_ids:
            items.append(RecommendationItem(
                component=candidate, selected=False,
                reasons=["not relevant to inferred capabilities"],
            ))

    return RecommendationPlan(interview=answer, capabilities=capabilities, items=items)
