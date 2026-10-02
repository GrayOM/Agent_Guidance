from pydantic import BaseModel, Field

from .capability import Capability
from .component import Component
from .interview import InterviewAnswer
from .risk import ConflictFinding, RiskLevel, SecurityFinding


class RecommendationItem(BaseModel):
    component: Component
    selected: bool
    reasons: list[str]


class RecommendationPlan(BaseModel):
    interview: InterviewAnswer
    capabilities: set[Capability]
    items: list[RecommendationItem]
    conflicts: list[ConflictFinding] = Field(default_factory=list)
    security_findings: list[SecurityFinding] = Field(default_factory=list)

    @property
    def overall_risk(self) -> RiskLevel:
        return RiskLevel.WARNING if any(
            finding.level == RiskLevel.WARNING for finding in self.security_findings
        ) else RiskLevel.LOW

    @property
    def selected(self) -> list[Component]:
        return [item.component for item in self.items if item.selected]

    @property
    def uncovered_capabilities(self) -> set[Capability]:
        covered = set().union(*(component.capabilities for component in self.selected)) if self.selected else set()
        return self.capabilities - covered
