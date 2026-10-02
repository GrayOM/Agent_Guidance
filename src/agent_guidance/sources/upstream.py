"""Resolve the reference a managed component's upstream currently publishes.

`agent-guidance update` previously compared an installed component against the Local Registry's
pinned refs, so a component only ever appeared out of date when Agent Guidance itself shipped a new
Registry. A component discovered on GitHub was never comparable at all. This resolves what
upstream publishes right now, so "up to date" means up to date with the source.

The comparison follows how the component was pinned, because changing the pinning style
would change what a later install resolves to:

- pinned to a commit -> the head commit of the default branch
- pinned to a tag    -> the latest published release

One request per component. A component whose upstream cannot be reached is reported as
unchecked with a reason, never as unchanged, so the caller can fall back to the Registry
instead of silently claiming the component is current.
"""

import asyncio
import os
import re
from typing import Literal

import httpx
from pydantic import BaseModel

from agent_guidance import __version__
from agent_guidance.network import create_async_client


COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_URL = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

Pinning = Literal["commit", "release"]


class UpstreamRef(BaseModel):
    component_id: str
    current_ref: str | None = None
    latest_ref: str | None = None
    pinning: Pinning | None = None
    checked: bool = False
    reason: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.checked and self.latest_ref and self.latest_ref != self.current_ref)

    def describe(self) -> str:
        if self.changed:
            source = "release" if self.pinning == "release" else "commit"
            return f"upstream {source} changed"
        return self.reason or "upstream matches the installed reference"


def parse_repository(url: str | None) -> tuple[str, str] | None:
    """Return (owner, name) for a GitHub HTTPS URL, or None for anything else."""
    match = REPOSITORY_URL.match((url or "").strip())
    return (match.group("owner"), match.group("name")) if match else None


def pinning_of(ref: str | None) -> Pinning | None:
    if not ref:
        return None
    return "commit" if COMMIT_SHA.match(ref) else "release"


class UpstreamResolver:
    """Reads the current upstream reference for installed components."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 5) -> None:
        self.client = client
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"agent-guidance/{__version__}",
        }
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _get(self, client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        return await client.get(url, headers=self._headers(), **kwargs)

    async def _resolve_one(self, client: httpx.AsyncClient, managed) -> UpstreamRef:
        current = managed.source_ref
        pinning = pinning_of(current)
        result = UpstreamRef(
            component_id=managed.component_id, current_ref=current, pinning=pinning,
        )
        if not pinning:
            result.reason = "no installed reference is recorded"
            return result
        repository = parse_repository(managed.source_repository)
        if not repository:
            result.reason = "upstream is not a GitHub HTTPS repository"
            return result
        owner, name = repository
        try:
            if pinning == "commit":
                response = await self._get(
                    client, f"/repos/{owner}/{name}/commits", params={"per_page": 1},
                )
                response.raise_for_status()
                commits = response.json()
                latest = commits[0].get("sha") if isinstance(commits, list) and commits else None
            else:
                response = await self._get(client, f"/repos/{owner}/{name}/releases/latest")
                if response.status_code == 404:
                    result.reason = "upstream publishes no release to compare against"
                    return result
                response.raise_for_status()
                latest = response.json().get("tag_name")
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            result.reason = f"upstream could not be checked: {exc.__class__.__name__}"
            return result
        if not latest:
            result.reason = "upstream returned no reference"
            return result
        result.latest_ref = str(latest)
        result.checked = True
        return result

    async def resolve(self, managed_components: list) -> dict[str, UpstreamRef]:
        if not managed_components:
            return {}
        if self.client is not None:
            results = await asyncio.gather(
                *(self._resolve_one(self.client, item) for item in managed_components)
            )
        else:
            async with create_async_client(
                base_url="https://api.github.com", timeout=self.timeout,
            ) as client:
                results = await asyncio.gather(
                    *(self._resolve_one(client, item) for item in managed_components)
                )
        return {item.component_id: item for item in results}


def resolve_upstream_refs(
    managed_components: list, client: httpx.AsyncClient | None = None,
) -> dict[str, UpstreamRef]:
    """Synchronous entry point; a transport failure yields an empty result, never an error."""
    try:
        return asyncio.run(UpstreamResolver(client=client).resolve(managed_components))
    except (httpx.HTTPError, OSError, RuntimeError):
        return {}
