from abc import ABC, abstractmethod

from grayom_agent_guidance.models import Component


class ComponentSource(ABC):
    @abstractmethod
    async def discover(self, query: str) -> list[Component]: ...

