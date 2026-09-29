from .base import ComponentSource


class OfficialSource(ComponentSource):
    async def discover(self, query: str):
        raise NotImplementedError("official source discovery is outside the MVP")

