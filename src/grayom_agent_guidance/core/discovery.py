import asyncio
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from grayom_agent_guidance.models import (
    Component, ComponentType, InterviewAnswer, InstallKind, SourceType,
)
from grayom_agent_guidance.sources.base import SourceResult, SourceUnavailable
from grayom_agent_guidance.sources.cache import CandidateCache
from grayom_agent_guidance.sources.github import GitHubSource
from grayom_agent_guidance.sources.official import OfficialSource
from grayom_agent_guidance.sources.registry import RegistrySource
from grayom_agent_guidance.sources.validator import ComponentValidator

from .capability_inference import infer_capabilities
from .query_builder import build_queries


class DiscoveryResult(BaseModel):
    candidates: list[Component]
    sources: list[SourceResult]
    warnings: list[str] = Field(default_factory=list)
    offline_fallback: bool = False

    @property
    def discovered(self) -> int:
        return sum(source.discovered for source in self.sources)

    @property
    def validated(self) -> int:
        return sum(component.recommendable for component in self.candidates)


def _rank(component: Component) -> tuple[int, int, int]:
    source_rank = {
        SourceType.OFFICIAL: 4,
        SourceType.REGISTRY: 3,
        SourceType.GITHUB: 2,
        SourceType.CACHE: 1,
    }.get(component.trust.source_type, 0)
    return (
        source_rank + (2 if component.trust.official else 0),
        int(component.trust.verified),
        int(component.recommendable),
    )


def _merge_candidates(candidates: list[Component]) -> list[Component]:
    merged: dict[tuple[str, str], Component] = {}
    for candidate in candidates:
        key = (str(candidate.github_url).rstrip("/").lower(), candidate.type.value)
        current = merged.get(key)
        if current is None:
            merged[key] = candidate.model_copy(deep=True)
            continue
        preferred, secondary = (candidate, current) if _rank(candidate) > _rank(current) else (current, candidate)
        combined = preferred.model_copy(deep=True)
        combined.capabilities |= secondary.capabilities
        combined.supported_agents |= secondary.supported_agents
        combined.conflicts |= secondary.conflicts
        combined.overlaps |= secondary.overlaps
        combined.evidence.extend(item for item in secondary.evidence if item not in combined.evidence)
        combined.validation_warnings = list(dict.fromkeys(
            combined.validation_warnings + secondary.validation_warnings
        ))
        if combined.install_method.kind == InstallKind.NONE:
            combined.install_method = secondary.install_method
        elif (
            combined.install_method.kind == InstallKind.MCP_HTTP
            and not combined.install_method.bearer_token_env_var
            and secondary.install_method.bearer_token_env_var
        ):
            combined.install_method.bearer_token_env_var = secondary.install_method.bearer_token_env_var
        if secondary.id == "github" or secondary.source == "local_registry":
            # Stable curated ids keep existing installation/config compatibility.
            combined.id = secondary.id
        merged[key] = combined
    return list(merged.values())


async def discover_components(
    answer: InterviewAnswer,
    *,
    offline: bool = False,
    cache_path: Path | None = None,
    github_client: httpx.AsyncClient | None = None,
) -> DiscoveryResult:
    capabilities = infer_capabilities(answer)
    cache = CandidateCache(path=cache_path)
    registry_result = await RegistrySource().discover()
    if offline:
        cached = cache.verified_components()
        for component in cached:
            component.trust.source_type = SourceType.CACHE
        return DiscoveryResult(
            candidates=_merge_candidates(registry_result.candidates + cached),
            sources=[registry_result, SourceResult(
                source="cache", checked=True, candidates=cached,
                discovered=len(cached), validated=sum(item.recommendable for item in cached),
            )],
            warnings=["Live component discovery disabled; using local registry and verified cache."],
            offline_fallback=True,
        )

    queries: list[str] = []
    for component_type in ComponentType:
        queries.extend(build_queries(answer.agents, capabilities, component_type, limit=1))
    validator = ComponentValidator(set(answer.agents))
    official = OfficialSource(
        validator=validator, cache=cache, client=github_client,
        selected_agents=set(answer.agents),
    )
    github = GitHubSource(validator=validator, cache=cache, client=github_client)
    tasks = [
        asyncio.wait_for(official.discover([]), timeout=25),
        asyncio.wait_for(github.discover(queries), timeout=25),
    ]
    live_results = await asyncio.gather(*tasks, return_exceptions=True)
    sources = [registry_result]
    warnings: list[str] = []
    live_candidates: list[Component] = []
    failed = 0
    for name, result in zip(("official", "github"), live_results):
        if isinstance(result, BaseException):
            failed += 1
            safe_message = str(result) or (
                "discovery timed out after 25 seconds" if isinstance(result, TimeoutError)
                else result.__class__.__name__
            )
            warnings.append(f"{name} discovery unavailable: {safe_message}")
            sources.append(SourceResult(source=name, checked=False, warnings=[safe_message]))
        else:
            sources.append(result)
            live_candidates.extend(result.candidates)
            warnings.extend(result.warnings)

    fallback = failed > 0
    cached = cache.verified_components() if fallback else []
    if fallback:
        warnings.append("Using last verified component cache where available.")
        sources.append(SourceResult(
            source="cache", checked=True, candidates=cached,
            discovered=len(cached), validated=sum(item.recommendable for item in cached),
        ))
    candidates = _merge_candidates(registry_result.candidates + live_candidates + cached)
    return DiscoveryResult(
        candidates=candidates, sources=sources, warnings=warnings,
        offline_fallback=fallback,
    )


def discover_components_sync(answer: InterviewAnswer, **kwargs) -> DiscoveryResult:
    try:
        return asyncio.run(discover_components(answer, **kwargs))
    except (SourceUnavailable, httpx.HTTPError, OSError) as exc:
        cache = CandidateCache(path=kwargs.get("cache_path"))
        registry = asyncio.run(RegistrySource().discover())
        cached = cache.verified_components()
        return DiscoveryResult(
            candidates=_merge_candidates(registry.candidates + cached),
            sources=[registry], warnings=[f"Live component discovery unavailable: {exc}"],
            offline_fallback=True,
        )
