from grayom_agent_guidance.registry import load_registry

from .base import SourceResult


class RegistrySource:
    name = "registry"

    async def discover(self, queries: list[str] | None = None) -> SourceResult:
        del queries
        candidates = load_registry()
        return SourceResult(
            source=self.name, checked=True, candidates=candidates,
            discovered=len(candidates), validated=sum(item.recommendable for item in candidates),
        )
