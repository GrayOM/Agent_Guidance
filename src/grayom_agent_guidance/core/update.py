import json
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from grayom_agent_guidance.adapters import AgentAdapter
from grayom_agent_guidance.models import AgentType, Component, ComponentType, Ownership
from grayom_agent_guidance.runtime import PathSecurityError, validate_managed_path
from grayom_agent_guidance.sources.upstream import UpstreamRef
from grayom_agent_guidance.state import ManagedComponent, StateStore


class UpdateItem(BaseModel):
    component: Component
    agents: list[AgentType]
    current_ref: str | None
    target_ref: str | None
    reason: str
    warnings: list[str] = Field(default_factory=list)


class UpdatePlan(BaseModel):
    items: list[UpdateItem] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)


class UpdateResult(BaseModel):
    success: bool
    updated: list[str] = Field(default_factory=list)
    error: str | None = None
    rollback_errors: list[str] = Field(default_factory=list)


def _modification_warnings(managed: ManagedComponent) -> list[str]:
    warnings = []
    for filename, expected_hash in managed.file_hashes.items():
        path = Path(filename)
        if not path.is_file():
            warnings.append(f"managed file is missing: {path}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            warnings.append(f"file was modified after GrayOM installed it: {path}")
    return warnings


def _at_reference(component: Component, ref: str) -> Component:
    """The component as it would be installed at ref, so the transaction applies that ref."""
    updated = component.model_copy(deep=True)
    updated.install_method = updated.install_method.model_copy(update={"ref": ref})
    return updated


def build_update_plan(
    state: StateStore,
    candidates: list[Component],
    upstream: dict[str, UpstreamRef] | None = None,
) -> UpdatePlan:
    """Plan updates for GrayOM-managed components.

    Upstream is authoritative when it could be read: it is what the source publishes now.
    The Local Registry is the fallback for a component whose upstream could not be checked,
    which keeps an offline run working exactly as it did before.
    """
    available = {component.id: component for component in candidates}
    upstream = upstream or {}
    plan = UpdatePlan()
    for component_id, managed in sorted(state.document.components.items()):
        if managed.ownership == Ownership.EXISTING:
            continue
        installed = managed.to_component()
        reference = upstream.get(component_id)

        if reference and reference.checked:
            if not reference.changed:
                plan.unchanged.append(f"{component_id}: up to date with upstream")
                continue
            base = installed or available.get(component_id)
            if not base:
                plan.unchanged.append(
                    f"{component_id}: upstream moved to {reference.latest_ref} but the installed "
                    "component cannot be rebuilt from state or the Registry"
                )
                continue
            target = str(reference.latest_ref)
            plan.items.append(UpdateItem(
                component=_at_reference(base, target), agents=managed.agents,
                current_ref=managed.source_ref, target_ref=target,
                reason=reference.describe(), warnings=_modification_warnings(managed),
            ))
            continue

        component = available.get(component_id)
        if not component:
            unreachable = f"; {reference.reason}" if reference and reference.reason else ""
            plan.unchanged.append(
                f"{component_id}: source is not currently available{unreachable}"
            )
            continue
        target = component.install_method.ref
        if target and target != managed.source_ref:
            plan.items.append(UpdateItem(
                component=component, agents=managed.agents, current_ref=managed.source_ref,
                target_ref=target, reason="verified Registry reference changed",
                warnings=_modification_warnings(managed),
            ))
        else:
            plan.unchanged.append(f"{component_id}: up to date")
    return plan


def _managed_paths(adapter: AgentAdapter, component_id: str) -> list[Path]:
    state = adapter.inspect()
    roots = []
    for value in state.get("skills", []):
        path = Path(value)
        marker = path / ".grayom-component.json"
        if marker.exists():
            try:
                if json.loads(marker.read_text(encoding="utf-8")).get("component_id") == component_id:
                    roots.append(path)
            except (OSError, ValueError):
                pass
    plugins_root = state.get("plugins_root")
    if plugins_root:
        root = Path(str(plugins_root))
        candidate = root / component_id
        try:
            validate_managed_path(candidate, root)
        except PathSecurityError:
            return roots
        if (candidate / ".grayom-component.json").exists():
            roots.append(candidate)
    return roots


class UpdateTransaction:
    def __init__(self, adapters: dict[AgentType, AgentAdapter], backup_root: Path) -> None:
        self.adapters = adapters
        self.backup_root = backup_root

    def execute(self, plan: UpdatePlan) -> UpdateResult:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        root = self.backup_root / f"update-{stamp}"
        moved: list[tuple[Path, Path]] = []
        backups = {}
        try:
            affected = list(dict.fromkeys(agent for item in plan.items for agent in item.agents))
            for agent in affected:
                backups[agent] = self.adapters[agent].backup(root / agent.value)
            for item in plan.items:
                for agent in item.agents:
                    adapter = self.adapters[agent]
                    paths = _managed_paths(adapter, item.component.id)
                    asset_root = root / "assets" / agent.value / item.component.id
                    asset_root.mkdir(parents=True, exist_ok=True)
                    for index, path in enumerate(paths):
                        destination = asset_root / f"{index}-{path.name}"
                        shutil.move(path, destination)
                        moved.append((destination, path))
                    if item.component.type == ComponentType.SKILL:
                        adapter.install_skill(item.component)
                    elif item.component.type == ComponentType.PLUGIN:
                        adapter.install_plugin(item.component)
                    else:
                        adapter.configure_mcp(item.component)
                    health = adapter.health_check([item.component], probe_mcp=False)
                    if not health.healthy:
                        raise RuntimeError(f"Health Check failed for {agent.value}/{item.component.id}")
            return UpdateResult(success=True, updated=[item.component.id for item in plan.items])
        except Exception as exc:
            errors = []
            for backup, original in reversed(moved):
                try:
                    if original.exists():
                        shutil.rmtree(original)
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(backup, original)
                except OSError as rollback_exc:
                    errors.append(str(rollback_exc))
            for agent, backup in backups.items():
                from grayom_agent_guidance.models import InstallationManifest
                result = self.adapters[agent].rollback(InstallationManifest(backup=backup))
                errors.extend(result.errors)
            return UpdateResult(success=False, error=str(exc), rollback_errors=errors)
