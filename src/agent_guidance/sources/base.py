from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from agent_guidance.models import Component, ComponentType, SourceType


class RawCandidate(BaseModel):
    component_id: str | None = None
    repository_full_name: str
    repository_url: str
    source_type: SourceType
    metadata: dict[str, Any] = Field(default_factory=dict)
    readme: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
    tree_paths: list[str] = Field(default_factory=list)
    expected_type: ComponentType | None = None
    official_hint: bool = False
    verification_reason: str | None = None
    source_version: str | None = None


class SourceResult(BaseModel):
    source: str
    checked: bool = False
    candidates: list[Component] = Field(default_factory=list)
    discovered: int = 0
    validated: int = 0
    warnings: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None


class SourceUnavailable(RuntimeError):
    pass


class ComponentSource(ABC):
    name: str

    @abstractmethod
    async def search(self, queries: list[str]) -> list[RawCandidate]: ...

    @abstractmethod
    async def fetch(self, candidate: RawCandidate) -> RawCandidate: ...

    @abstractmethod
    def normalize(self, candidate: RawCandidate) -> Component: ...

    @abstractmethod
    def validate(self, component: Component) -> Component: ...

    async def discover(self, queries: list[str]) -> SourceResult:
        raw_candidates = await self.search(queries)
        result = SourceResult(source=self.name, checked=True, discovered=len(raw_candidates))
        for raw in raw_candidates:
            try:
                fetched = await self.fetch(raw)
                component = self.validate(self.normalize(fetched))
                result.candidates.append(component)
                if component.recommendable:
                    result.validated += 1
            except Exception as exc:
                result.warnings.append(f"{raw.repository_full_name}: {exc}")
        return result
