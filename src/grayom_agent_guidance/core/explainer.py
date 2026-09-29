from enum import StrEnum

from pydantic import BaseModel, Field

from grayom_agent_guidance.models import AgentType, Capability, RecommendationPlan
from .capability_inference import DOMAIN_CAPABILITIES, TASK_CAPABILITIES


class EvidenceType(StrEnum):
    OFFICIAL_DOC = "OFFICIAL_DOC"
    README = "README"
    MANIFEST = "MANIFEST"
    GITHUB_METADATA = "GITHUB_METADATA"
    REGISTRY = "REGISTRY"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"


class Confidence(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class ComponentExplanation(BaseModel):
    component_id: str
    reasons: list[str]
    why_selected: list[str]
    applies_to: list[AgentType]
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.NORMAL


class PlanExplanation(BaseModel):
    summary: list[str]
    components: list[ComponentExplanation]


def _origins(plan: RecommendationPlan, capabilities: set[Capability]) -> list[str]:
    origins = []
    for domain in plan.interview.domains:
        if DOMAIN_CAPABILITIES.get(domain, set()) & capabilities:
            origins.append(domain.value.replace("_", " ").title())
    for task in plan.interview.tasks:
        if TASK_CAPABILITIES.get(task, set()) & capabilities:
            origins.append(task.replace("_", " ").title())
    return list(dict.fromkeys(origins))


def explain_plan(plan: RecommendationPlan) -> PlanExplanation:
    summaries = []
    capability_messages = {
        Capability.REPOSITORY_ACCESS: "Repository access is required for source review and code workflows.",
        Capability.SECURITY_ANALYSIS: "Security analysis support was selected for the requested assessment work.",
        Capability.TESTING: "Testing support was added for validation and reproduction.",
        Capability.REPORTING: "Reporting support was selected for producing review results.",
        Capability.BROWSER_AUTOMATION: "Browser automation was inferred from the selected browser or OSINT work.",
    }
    for capability in sorted(plan.capabilities, key=lambda item: item.value):
        if capability in capability_messages:
            summaries.append(capability_messages[capability])
    explanations = []
    for item in plan.items:
        if not item.selected:
            continue
        component = item.component
        covered = component.capabilities & plan.capabilities
        origins = _origins(plan, covered)
        why = [
            f"Covers {len(covered)} required " + ("capabilities" if len(covered) != 1 else "capability"),
            "Deterministic policy preferred this candidate over lower-ranked alternatives",
        ]
        if component.trust.official:
            why.append("Official implementation")
        elif component.trust.verified:
            why.append("Repository evidence validated")
        limitations = list(component.validation_warnings)
        applies = [agent for agent in plan.interview.agents if agent in component.supported_agents]
        confidence = Confidence.HIGH if component.trust.official else (
            Confidence.NORMAL if component.trust.verified else Confidence.LOW
        )
        explanations.append(ComponentExplanation(
            component_id=component.id,
            reasons=[
                "Selected for " + ", ".join(sorted(capability.value for capability in covered)),
                "Inferred from: " + (", ".join(origins) if origins else "selected workflow"),
            ],
            why_selected=why, applies_to=applies, limitations=limitations,
            confidence=confidence,
        ))
    if plan.uncovered_capabilities:
        summaries.append(
            "No verified candidate covers: "
            + ", ".join(sorted(item.value for item in plan.uncovered_capabilities))
        )
    return PlanExplanation(summary=summaries, components=explanations)
