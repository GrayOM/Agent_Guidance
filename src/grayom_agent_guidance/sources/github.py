from .base import ComponentSource


class GitHubSource(ComponentSource):
    async def discover(self, query: str):
        raise NotImplementedError("GitHub live discovery is outside the MVP")

