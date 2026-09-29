from grayom_agent_guidance.models import (
    Component, InterviewAnswer, RecommendationItem, RecommendationPlan, SetupMode,
)

from .capability_inference import infer_capabilities


def recommend(answer: InterviewAnswer, candidates: list[Component]) -> RecommendationPlan:
    capabilities = infer_capabilities(answer)
    compatible = [
        item for item in candidates
        if set(answer.agents).issubset(item.compatibility.agents)
        and item.capabilities & capabilities
    ]
    compatible.sort(
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
    for candidate in compatible:
        new_coverage = (candidate.capabilities & capabilities) - covered
        overlaps = candidate.capabilities & covered
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
            reasons.append("overlaps with selected components")
        items.append(RecommendationItem(component=candidate, selected=choose, reasons=reasons))

    return RecommendationPlan(interview=answer, capabilities=capabilities, items=items)

