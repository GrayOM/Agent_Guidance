import shutil

from agent_guidance.models import Component, SharedComponentRecord


class SharedComponentManager:
    """Prepares shared runtime requirements once; Agent references remain adapter-specific."""

    def __init__(self) -> None:
        self.prepared: set[str] = set()

    def prepare(self, component: Component, record: SharedComponentRecord) -> list[str]:
        if component.id in self.prepared:
            return []
        self.prepared.add(component.id)
        record.prepared_count = 1
        warnings = []
        for dependency in component.dependencies:
            if dependency.required and shutil.which(dependency.executable) is None:
                warnings.append(
                    f"{component.name} dependency is unavailable: {dependency.executable}"
                )
        return warnings
