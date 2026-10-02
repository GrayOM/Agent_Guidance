import httpx

from agent_guidance import __version__


def create_async_client(
    *, base_url: str = "", timeout: float = 5, headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    merged = {"User-Agent": f"agent-guidance/{__version__}"}
    if headers:
        merged.update(headers)
    return httpx.AsyncClient(
        base_url=base_url, timeout=httpx.Timeout(timeout), follow_redirects=True,
        headers=merged, trust_env=True,
    )
