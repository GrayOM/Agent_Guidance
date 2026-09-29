import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import grayom_home
from .models import AgentType, MultiAgentManifest, MultiAgentPlan, Ownership


class ManagedComponent(BaseModel):
    component_id: str
    agents: list[AgentType]
    ownership: Ownership
    source_ref: str | None = None
    transaction_id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StateDocument(BaseModel):
    schema_version: int = 1
    components: dict[str, ManagedComponent] = Field(default_factory=dict)
    transactions: list[str] = Field(default_factory=list)


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or grayom_home() / "state" / "components.json"
        self.document = self._load()

    def _load(self) -> StateDocument:
        if not self.path.exists():
            return StateDocument()
        try:
            return StateDocument.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return StateDocument()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(self.document.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, plan: MultiAgentPlan, manifest: MultiAgentManifest) -> None:
        usage: dict[str, list[AgentType]] = {}
        components = {}
        existing_by_component: dict[str, list[bool]] = {}
        for agent, agent_plan in plan.agents.items():
            for action in agent_plan.actions:
                if action.install or action.already_installed:
                    usage.setdefault(action.component.id, []).append(agent)
                    components[action.component.id] = action.component
                    existing_by_component.setdefault(action.component.id, []).append(action.already_installed)
        shared = {item.component_id: item for item in plan.shared_components}
        for component_id, agents in usage.items():
            component = components[component_id]
            ownership = (
                Ownership.EXISTING if all(existing_by_component.get(component_id, []))
                else shared.get(component_id).ownership if component_id in shared
                else Ownership.GRAYOM_INSTALLED
            )
            self.document.components[component_id] = ManagedComponent(
                component_id=component_id, agents=agents, ownership=ownership,
                source_ref=component.install_method.ref, transaction_id=manifest.transaction_id,
            )
        if str(manifest.path) not in self.document.transactions:
            self.document.transactions.append(str(manifest.path))
        self.save()
