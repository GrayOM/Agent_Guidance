import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from grayom_agent_guidance.models import (
    AdapterCapabilities, AgentInstallation, AgentType, BackupEntry, BackupManifest, CheckResult, Component,
    ComponentInstallResult, ComponentType, HealthCheckResult, HealthLevel, InstallationManifest,
    RollbackResult,
)
from grayom_agent_guidance.runtime import ProcessRunner, validate_managed_path

from .base import AgentAdapter
from .codex import MCP_DIFFERENT_SETTINGS_REASON, AdapterError, _safe_name
from .json_support import desired_json_mcp, install_git_skills, merge_mcp, read_json_object


class CursorAdapter(AgentAdapter):
    """Limits writes to Cursor's documented AI customization directories."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        # Official docs define plugin manifests and Marketplace distribution, but do not document
        # a stable user directory that GrayOM can mutate transactionally.
        return AdapterCapabilities(skills=True, mcp=True, plugins=False, health_probe=False)

    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        self.cursor_home = self.home / ".cursor"
        self.config_path = self.cursor_home / "mcp.json"
        self.skills_root = self.cursor_home / "skills"
        self.plugins_root = self.cursor_home / "plugins" / "local"

    def detect(self) -> AgentInstallation:
        executable = shutil.which("cursor") or shutil.which("cursor-agent")
        version = None
        if executable:
            try:
                version = ProcessRunner().run([executable, "--version"], timeout=3).stdout.strip().splitlines()[0] or None
            except (OSError, RuntimeError, IndexError):
                pass
        detected = bool(executable or self.cursor_home.exists())
        return AgentInstallation(
            agent=AgentType.CURSOR, detected=detected,
            executable=Path(executable) if executable else None,
            config_path=self.config_path if self.config_path.exists() else None,
            version=version, details={"scope": "user"},
        )

    def get_version(self) -> str | None:
        return self.detect().version

    def get_config_paths(self) -> list[Path]:
        return [self.config_path]

    def list_existing_skills(self) -> list[str]:
        return sorted(path.parent.name for path in self.skills_root.glob("**/SKILL.md")) if self.skills_root.exists() else []

    def list_existing_mcps(self) -> list[str]:
        return sorted((read_json_object(self.config_path).get("mcpServers") or {}).keys())

    def list_existing_plugins(self) -> list[str]:
        if not self.plugins_root.exists():
            return []
        return sorted(path.name for path in self.plugins_root.iterdir() if path.is_dir())

    def inspect(self) -> dict[str, object]:
        skill_paths = sorted(path.parent for path in self.skills_root.glob("**/SKILL.md")) if self.skills_root.exists() else []
        return {
            "config_paths": self.get_config_paths(), "skills_root": self.skills_root,
            "plugins_root": self.plugins_root, "skills": skill_paths,
            "mcp_servers": self.list_existing_mcps(), "plugins": self.list_existing_plugins(),
        }

    def existing_component_status(self, component: Component) -> tuple[bool, str | None]:
        if component.type == ComponentType.SKILL:
            prefix = f"{_safe_name(component.id)}--"
            exists = any(name.startswith(prefix) for name in self.list_existing_skills())
            return exists, "existing Cursor Skill preserved" if exists else None
        if component.type == ComponentType.PLUGIN:
            exists = _safe_name(component.id) in self.list_existing_plugins()
            return exists, "existing Cursor Plugin preserved" if exists else None
        if component.type == ComponentType.MCP:
            servers = read_json_object(self.config_path).get("mcpServers") or {}
            existing = servers.get(component.id) if isinstance(servers, dict) else None
            if existing == desired_json_mcp(component, cursor=True):
                return True, "compatible Cursor MCP registration already exists"
            desired = desired_json_mcp(component, cursor=True)
            if isinstance(servers, dict) and any(
                value == desired for name, value in servers.items()
                if name.startswith(f"{component.id}-grayom")
            ):
                return True, "compatible GrayOM MCP alias already exists"
            if existing is not None:
                return True, MCP_DIFFERENT_SETTINGS_REASON
        return False, None

    def backup(self, destination: Path) -> BackupManifest:
        destination.mkdir(parents=True, exist_ok=False)
        destination.chmod(0o700)
        entry = BackupEntry(original=self.config_path, existed=self.config_path.exists())
        if self.config_path.exists():
            target = destination / "mcp.json"
            shutil.copy2(self.config_path, target)
            entry.backup = target
        return BackupManifest(root=destination, entries=[entry])

    def install_skill(self, component: Component) -> ComponentInstallResult:
        return install_git_skills(component, self.skills_root)

    def configure_mcp(self, component: Component) -> ComponentInstallResult:
        return merge_mcp(self.config_path, component, cursor=True)

    def install_plugin(self, component: Component) -> ComponentInstallResult:
        raise AdapterError(
            "Cursor Plugin installation requires an official Marketplace/API flow; "
            "GrayOM will not write to an undocumented local plugin path"
        )

    def health_check(self, expected: list[Component] | None = None, probe_mcp: bool = True) -> HealthCheckResult:
        del probe_mcp
        expected = expected or []
        detection = self.detect()
        checks = [CheckResult(
            name="cursor_detected", passed=detection.detected,
            message="Cursor executable or configuration detected" if detection.detected else "Cursor was not detected",
        )]
        try:
            config = read_json_object(self.config_path)
            checks.append(CheckResult(name="cursor_config_parse", passed=True, message="Cursor mcp.json is valid"))
        except AdapterError as exc:
            checks.append(CheckResult(name="cursor_config_parse", passed=False, message=str(exc)))
            return HealthCheckResult(checks=checks)
        servers = config.get("mcpServers") or {}
        markers: set[str] = set()
        for root in (self.skills_root, self.plugins_root):
            for marker in root.glob("**/.grayom-component.json") if root.exists() else []:
                try:
                    markers.add(json.loads(marker.read_text(encoding="utf-8"))["component_id"])
                except (OSError, ValueError, KeyError):
                    pass
        for component in expected:
            if component.type in {ComponentType.SKILL, ComponentType.PLUGIN}:
                checks.append(CheckResult(
                    name=f"cursor_{component.type.value}_discovery:{component.id}", passed=component.id in markers,
                    message="component discovery metadata found" if component.id in markers else "component was not discoverable",
                    level=HealthLevel.INITIALIZATION,
                ))
            elif component.type == ComponentType.MCP:
                desired = desired_json_mcp(component, cursor=True)
                registered = next((value for value in servers.values() if value == desired), None) if isinstance(servers, dict) else None
                checks.append(CheckResult(
                    name=f"cursor_mcp_config:{component.id}", passed=registered is not None,
                    message="MCP registration found" if registered is not None else "MCP registration missing",
                ))
                if registered and "url" in registered:
                    parsed = urlparse(str(registered["url"]))
                    checks.append(CheckResult(
                        name=f"cursor_mcp_endpoint:{component.id}", passed=parsed.scheme == "https" and bool(parsed.netloc),
                        message="MCP HTTPS endpoint is valid",
                        level=HealthLevel.INITIALIZATION,
                    ))
                elif registered and "command" in registered:
                    available = shutil.which(str(registered["command"])) is not None
                    checks.append(CheckResult(
                        name=f"cursor_mcp_process:{component.id}", passed=available,
                        message="MCP command is executable" if available else "MCP command not found",
                        level=HealthLevel.INITIALIZATION,
                    ))
        return HealthCheckResult(checks=checks)

    def rollback(self, manifest: InstallationManifest) -> RollbackResult:
        result = RollbackResult()
        allowed = [self.skills_root.resolve(), self.plugins_root.resolve()]
        for path in reversed(manifest.created_paths):
            try:
                root = next((item for item in allowed if path.resolve(strict=False).is_relative_to(item)), None)
                if root is None:
                    raise AdapterError(f"refusing to remove unmanaged path: {path}")
                validate_managed_path(path, root, allow_missing=False)
                resolved = path.resolve()
                if not any(resolved.is_relative_to(root) for root in allowed) or not (resolved / ".grayom-component.json").exists():
                    raise AdapterError(f"refusing to remove unmanaged path: {resolved}")
                shutil.rmtree(resolved)
            except (OSError, AdapterError) as exc:
                result.errors.append(str(exc))
        for entry in manifest.backup.entries:
            try:
                allowed_configs = {path.resolve(strict=False) for path in self.get_config_paths()}
                if entry.original.resolve(strict=False) not in allowed_configs:
                    raise AdapterError(f"refusing to restore unexpected config path: {entry.original}")
                if entry.existed:
                    if not entry.backup:
                        raise AdapterError(f"missing backup for {entry.original}")
                    entry.original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry.backup, entry.original)
                    result.restored.append(entry.original)
                else:
                    entry.original.unlink(missing_ok=True)
            except (OSError, AdapterError) as exc:
                result.errors.append(f"{entry.original}: {exc}")
        return result
