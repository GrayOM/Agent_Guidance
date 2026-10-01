import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import grayom_home
from .models import (
    AgentType, Component, ComponentType, InstallKind, InstallMethod, MultiAgentManifest,
    MultiAgentPlan, Ownership,
)
from .runtime import validate_managed_path
from .schema import load_versioned_json


class ManagedComponent(BaseModel):
    schema_version: int = 1
    component_id: str
    agents: list[AgentType]
    ownership: Ownership
    source_ref: str | None = None
    source_repository: str | None = None
    source_commit: str | None = None
    source_tag: str | None = None
    package_version: str | None = None
    installation_paths: list[Path] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
    security_warnings: list[str] = Field(default_factory=list)
    health_status: str = "NOT_VERIFIED"
    installed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Without these a component is identified by id alone, so one discovered on GitHub can be
    # installed and then never diagnosed again: Health Check needs its type and install method,
    # and neither is recoverable from the Local Registry. They stay optional, and absent in a
    # record an earlier GrayOM wrote, so reading existing state never discards ownership.
    component_name: str | None = None
    component_type: ComponentType | None = None
    install_method: InstallMethod | None = None

    def to_component(self) -> Component | None:
        """Rebuild the component as installed, or None when the record predates these fields."""
        if not self.component_type or not self.source_repository or not self.install_method:
            return None
        if self.install_method.kind == InstallKind.NONE:
            return None
        return Component(
            id=self.component_id, name=self.component_name or self.component_id,
            type=self.component_type, github_url=self.source_repository,
            supported_agents=set(self.agents), install_method=self.install_method,
            source="grayom_state",
        )


class StateDocument(BaseModel):
    schema_version: int = 1
    components: dict[str, ManagedComponent] = Field(default_factory=dict)
    transactions: list[str] = Field(default_factory=list)


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or grayom_home() / "state" / "components.json"
        self.warnings: list[str] = []
        self.document = self._load()

    def _load(self) -> StateDocument:
        if not self.path.exists():
            return StateDocument()
        try:
            return StateDocument.model_validate(load_versioned_json(self.path))
        except (OSError, ValueError) as exc:
            # A document written by a newer schema raises ConfigurationError, which is not
            # caught here and still refuses the run.
            self._set_damaged_document_aside(exc)
            return StateDocument()

    def _set_damaged_document_aside(self, exc: Exception) -> None:
        """Keep an unreadable document instead of letting the next save overwrite it.

        Ownership decides what update and rollback may touch, so losing these records would
        let GrayOM treat a user's own component as unmanaged.
        """
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        target = self.path.with_name(f"{self.path.name}.damaged-{stamp}")
        try:
            os.replace(self.path, target)
        except OSError as move_error:
            self.warnings.append(
                f"GrayOM state is unreadable and could not be set aside ({exc}); "
                f"refusing to discard it silently: {move_error}"
            )
            return
        self.warnings.append(
            f"GrayOM state was unreadable ({exc}) and has been kept as {target.name}. "
            "Components installed before now are no longer tracked as GrayOM-managed, so "
            "update and rollback will leave them alone."
        )

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
        self._save_component_manifests()

    def _save_component_manifests(self) -> None:
        root = self.path.parent / "component-manifests"
        root.mkdir(parents=True, exist_ok=True)
        for component_id, component in self.document.components.items():
            target = root / f"{component_id}.json"
            # The id is validated at the model boundary; containment is re-checked here because
            # this is the only managed write that derives a filename from component data.
            validate_managed_path(target, root)
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write(component.model_dump_json(indent=2))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                try:
                    target.chmod(0o600)
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
            paths: list[Path] = []
            hashes: dict[str, str] = {}
            for agent in agents:
                agent_manifest = manifest.agent_manifests.get(agent)
                if not agent_manifest:
                    continue
                for path in agent_manifest.created_paths:
                    marker = path / ".grayom-component.json"
                    try:
                        marker_value = json.loads(marker.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if marker_value.get("component_id") != component_id:
                        continue
                    paths.append(path)
                    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
                        hashes[str(file_path)] = hashlib.sha256(file_path.read_bytes()).hexdigest()
            ownership = (
                Ownership.EXISTING if all(existing_by_component.get(component_id, []))
                else shared.get(component_id).ownership if component_id in shared
                else Ownership.GRAYOM_INSTALLED
            )
            self.document.components[component_id] = ManagedComponent(
                component_id=component_id, agents=agents, ownership=ownership,
                source_ref=component.install_method.ref, transaction_id=manifest.transaction_id,
                component_name=component.name, component_type=component.type,
                install_method=component.install_method.model_copy(deep=True),
                source_repository=str(component.install_method.repository or component.github_url),
                source_commit=(component.install_method.ref if component.install_method.ref and len(component.install_method.ref) == 40 else None),
                source_tag=(component.install_method.ref if component.install_method.ref and len(component.install_method.ref) != 40 else None),
                installation_paths=paths, file_hashes=hashes,
                health_status="PASS" if manifest.completed else "NOT_VERIFIED",
            )
        if str(manifest.path) not in self.document.transactions:
            self.document.transactions.append(str(manifest.path))
        self.save()

    def refresh_hashes(self, component_id: str) -> None:
        component = self.document.components[component_id]
        hashes: dict[str, str] = {}
        for root in component.installation_paths:
            if not root.exists():
                continue
            for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
                hashes[str(file_path)] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        component.file_hashes = hashes
