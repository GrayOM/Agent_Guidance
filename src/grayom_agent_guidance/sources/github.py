import os
import asyncio
from pathlib import PurePosixPath
from typing import Any

import httpx

from grayom_agent_guidance import __version__
from grayom_agent_guidance.models import SourceType
from grayom_agent_guidance.network import create_async_client

from .base import ComponentSource, RawCandidate, SourceResult, SourceUnavailable
from .cache import CandidateCache
from .normalizer import normalize_candidate
from .validator import ComponentValidator


INTERESTING_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "dockerfile",
    "install.sh", "setup.sh", "update.sh", "upgrade.sh", "skill.md",
    "plugin.json", "mcp.json", "server.json",
}


class GitHubSource(ComponentSource):
    name = "github"

    def __init__(
        self,
        validator: ComponentValidator,
        cache: CandidateCache | None = None,
        client: httpx.AsyncClient | None = None,
        max_results_per_query: int = 3,
        max_candidates: int = 5,
    ) -> None:
        self.validator = validator
        self.cache = cache
        self.client = client
        self.max_results_per_query = max_results_per_query
        self.max_candidates = max_candidates
        self.rate_limit_remaining: int | None = None

    def _headers(self, raw: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"grayom-agent-guidance/{__version__}",
        }
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(self, method: str, url: str, *, raw: bool = False, **kwargs) -> httpx.Response:
        async def perform(client: httpx.AsyncClient) -> httpx.Response:
            response = None
            for attempt in range(2):
                try:
                    response = await client.request(method, url, headers=self._headers(raw), **kwargs)
                    break
                except httpx.TransportError:
                    if attempt:
                        raise
            assert response is not None
            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining and remaining.isdigit():
                self.rate_limit_remaining = int(remaining)
            if response.status_code in {403, 429}:
                raise SourceUnavailable(
                    f"GitHub API unavailable or rate limited (remaining={remaining or 'unknown'})"
                )
            response.raise_for_status()
            return response

        if self.client:
            return await perform(self.client)
        async with create_async_client(base_url="https://api.github.com", timeout=5) as client:
            return await perform(client)

    async def search(self, queries: list[str]) -> list[RawCandidate]:
        rate = (await self._request("GET", "/rate_limit")).json().get("resources", {}).get("search", {})
        remaining = rate.get("remaining")
        if isinstance(remaining, int):
            self.rate_limit_remaining = remaining
        if remaining == 0:
            raise SourceUnavailable("GitHub search rate limit exhausted")
        repositories: dict[str, RawCandidate] = {}
        async def search_one(query: str) -> httpx.Response:
            return await self._request(
                "GET", "/search/repositories",
                params={"q": query, "sort": "updated", "order": "desc", "per_page": self.max_results_per_query},
            )
        responses = await asyncio.gather(*(search_one(query) for query in queries))
        for response in responses:
            for item in response.json().get("items", []):
                full_name = item.get("full_name")
                html_url = item.get("html_url")
                if not full_name or not html_url or item.get("private"):
                    continue
                repositories.setdefault(full_name.lower(), RawCandidate(
                    repository_full_name=full_name, repository_url=html_url,
                    source_type=SourceType.GITHUB, metadata=item,
                    source_version=item.get("pushed_at"),
                ))
        ranked = sorted(
            repositories.values(),
            key=lambda item: (
                item.metadata.get("stargazers_count", 0), item.metadata.get("pushed_at", "")
            ),
            reverse=True,
        )
        return ranked[: self.max_candidates]

    async def _optional_json(self, url: str) -> dict[str, Any] | None:
        try:
            return (await self._request("GET", url)).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def _optional_text(self, url: str) -> str | None:
        try:
            response = await self._request("GET", url, raw=True)
            return response.text[:500_000]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def fetch(self, candidate: RawCandidate) -> RawCandidate:
        repo = candidate.repository_full_name
        initial_metadata = candidate.metadata
        branch = initial_metadata.get("default_branch") or "main"
        metadata_response, readme, commit, release, tree = await asyncio.gather(
            self._request("GET", f"/repos/{repo}"),
            self._optional_text(f"/repos/{repo}/readme"),
            self._optional_json(f"/repos/{repo}/commits/{branch}"),
            self._optional_json(f"/repos/{repo}/releases/latest"),
            self._optional_json(f"/repos/{repo}/git/trees/{branch}?recursive=1"),
        )
        metadata = metadata_response.json()
        candidate.metadata.update(metadata)
        candidate.readme = readme
        if commit and commit.get("sha"):
            candidate.metadata["head_sha"] = commit["sha"]
        if release:
            candidate.metadata["latest_release"] = release.get("published_at")
        tree = tree or {}
        candidate.tree_paths = [
            item["path"] for item in tree.get("tree", [])
            if item.get("type") == "blob" and item.get("path")
        ]
        interesting = [
            path for path in candidate.tree_paths
            if PurePosixPath(path).name.lower() in INTERESTING_FILES
        ][:16]
        contents = await asyncio.gather(*(
            self._optional_text(f"/repos/{repo}/contents/{path}") for path in interesting
        ))
        for path, content in zip(interesting, contents):
            if content is not None:
                candidate.files[path] = content[:250_000]
        return candidate

    def normalize(self, candidate: RawCandidate):
        return normalize_candidate(candidate)

    def validate(self, component):
        return self.validator.validate(component)

    async def discover(self, queries: list[str]) -> SourceResult:
        raw_candidates = await self.search(queries)
        result = SourceResult(source=self.name, checked=True, discovered=len(raw_candidates))
        semaphore = asyncio.Semaphore(3)

        async def process(raw: RawCandidate):
            async with semaphore:
                cached = (
                    self.cache.get(raw.repository_url, raw.source_version)
                    if self.cache and raw.source_version else None
                )
                if cached:
                    return self.validate(cached), raw.source_version, None
                fetched = await self.fetch(raw)
                return self.validate(self.normalize(fetched)), raw.source_version, None

        processed = await asyncio.gather(*(process(raw) for raw in raw_candidates), return_exceptions=True)
        for raw, outcome in zip(raw_candidates, processed):
            try:
                if isinstance(outcome, BaseException):
                    raise outcome
                component, source_version, _ = outcome
                if self.cache:
                    self.cache.put(component, self.name, source_version)
                result.candidates.append(component)
                if component.recommendable:
                    result.validated += 1
            except Exception as exc:
                result.warnings.append(f"{raw.repository_full_name}: {exc}")
        result.rate_limit_remaining = self.rate_limit_remaining
        if self.cache:
            self.cache.save()
        return result
