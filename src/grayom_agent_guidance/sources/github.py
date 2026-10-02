import os
import asyncio
from pathlib import PurePosixPath
from typing import Any

import httpx

from grayom_agent_guidance import __version__
from grayom_agent_guidance.models import SourceType
from grayom_agent_guidance.network import create_async_client

from .base import ComponentSource, RawCandidate, SourceResult, SourceUnavailable
from .budget import DiscoveryBudget
from .cache import CandidateCache
from .normalizer import normalize_candidate
from .validator import ComponentValidator


# A manifest decides what the repository is and how it can be installed, an install script
# decides whether that is safe, and the rest only refines the picture. The file budget is
# small on an anonymous run, so the list is read in that order rather than in tree order.
MANIFEST_FILES = ("marketplace.json", "plugin.json", "skill.md", "mcp.json", "server.json")
INSTALL_SCRIPT_FILES = ("install.sh", "setup.sh", "update.sh", "upgrade.sh")
SUPPORTING_FILES = ("package.json", "pyproject.toml", "requirements.txt", "dockerfile")
INTERESTING_FILES = {*MANIFEST_FILES, *INSTALL_SCRIPT_FILES, *SUPPORTING_FILES}


def _file_priority(path: str) -> int:
    name = PurePosixPath(path).name.lower()
    if name in MANIFEST_FILES:
        return 0
    return 1 if name in INSTALL_SCRIPT_FILES else 2


def describe_refusal(response: httpx.Response) -> str:
    """Say which of GitHub's three refusals this is, because the remedies differ.

    Reporting every 403 as a rate limit sends a user with an expired or narrowly scoped
    token away to wait an hour for something that will never change on its own. GitHub only
    signals a real rate limit through an exhausted remaining count, a Retry-After, or the
    phrase in its own message; a 403 with none of those is an access decision.
    """
    status = response.status_code
    remaining = response.headers.get("x-ratelimit-remaining")
    retry_after = response.headers.get("retry-after")
    try:
        detail = str(response.json().get("message") or "").strip()
    except ValueError:
        detail = ""
    suffix = f" GitHub said: {detail}" if detail else ""

    if status == 401:
        return (
            "GitHub rejected the credentials. Check GITHUB_TOKEN or GH_TOKEN, or unset it to "
            f"search anonymously.{suffix}"
        )
    rate_limited = (
        status == 429
        or remaining == "0"
        or bool(retry_after)
        or "rate limit" in detail.lower()
    )
    if rate_limited:
        window = f", retry after {retry_after}s" if retry_after else ""
        return (
            f"GitHub rate limit reached (remaining={remaining or 'unknown'}{window}). "
            f"Set GITHUB_TOKEN for a higher limit, or retry later.{suffix}"
        )
    return (
        "GitHub denied access rather than rate limiting: the token is missing a scope, the "
        "repository is not available to it, or the organisation requires SSO authorisation. "
        f"Waiting will not change this.{suffix}"
    )


def _repository_rank(candidate: RawCandidate) -> tuple[int, str, str]:
    return (
        candidate.metadata.get("stargazers_count", 0) or 0,
        str(candidate.metadata.get("pushed_at") or ""),
        candidate.repository_full_name,
    )


def _interleave(per_query: list[list[RawCandidate]], limit: int) -> list[RawCandidate]:
    """Take each query's best candidate before any query's second, up to the budget.

    Every capability the interview inferred therefore reaches the Plan, however few slots
    the request budget leaves.
    """
    if limit <= 0:
        return []
    selected: list[RawCandidate] = []
    for position in range(max((len(matches) for matches in per_query), default=0)):
        for matches in per_query:
            if position < len(matches):
                selected.append(matches[position])
                if len(selected) >= limit:
                    return selected
    return selected


class GitHubSource(ComponentSource):
    name = "github"

    def __init__(
        self,
        validator: ComponentValidator,
        cache: CandidateCache | None = None,
        client: httpx.AsyncClient | None = None,
        budget: DiscoveryBudget | None = None,
    ) -> None:
        self.validator = validator
        self.cache = cache
        self.client = client
        self.budget = budget or DiscoveryBudget.detect()
        self.rate_limit_remaining: int | None = None

    @property
    def max_results_per_query(self) -> int:
        return self.budget.results_per_query

    @property
    def max_candidates(self) -> int:
        return self.budget.max_candidates

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
            if response is None:
                raise SourceUnavailable("GitHub returned no response")
            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining and remaining.isdigit():
                self.rate_limit_remaining = int(remaining)
            if response.status_code in {401, 403, 429}:
                raise SourceUnavailable(describe_refusal(response))
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
        async def search_one(query: str) -> httpx.Response:
            return await self._request(
                "GET", "/search/repositories",
                params={"q": query, "sort": "updated", "order": "desc", "per_page": self.max_results_per_query},
            )
        responses = await asyncio.gather(*(search_one(query) for query in queries))

        # Each query targets one capability, so candidates are kept per query. Ranking the
        # whole pool by stars and truncating it let a few popular general-purpose
        # repositories crowd out every specialised capability the user actually asked about.
        seen: set[str] = set()
        per_query: list[list[RawCandidate]] = []
        for response in responses:
            matches: list[RawCandidate] = []
            for item in response.json().get("items", []):
                full_name = item.get("full_name")
                html_url = item.get("html_url")
                if not full_name or not html_url or item.get("private"):
                    continue
                if full_name.lower() in seen:
                    continue
                seen.add(full_name.lower())
                matches.append(RawCandidate(
                    repository_full_name=full_name, repository_url=html_url,
                    source_type=SourceType.GITHUB, metadata=item,
                    source_version=item.get("pushed_at"),
                ))
            matches.sort(key=_repository_rank, reverse=True)
            per_query.append(matches)
        return _interleave(per_query, self.max_candidates)

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
        interesting = sorted(
            (
                path for path in candidate.tree_paths
                if PurePosixPath(path).name.lower() in INTERESTING_FILES
            ),
            key=_file_priority,
        )[: self.budget.files_per_repository]
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
        failures: dict[str, list[str]] = {}
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
                failures.setdefault(str(exc), []).append(raw.repository_full_name)
        # One refusal that stopped every repository is one problem, not one per repository.
        for message, repositories in failures.items():
            if len(repositories) == 1:
                result.warnings.append(f"{repositories[0]}: {message}")
            else:
                result.warnings.append(f"{len(repositories)} repositories could not be read: {message}")
        result.rate_limit_remaining = self.rate_limit_remaining
        if self.cache:
            self.cache.save()
        return result
