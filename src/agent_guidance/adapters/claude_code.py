import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from agent_guidance.models import (
    AdapterCapabilities, AgentInstallation, AgentType, BackupEntry, BackupManifest, CheckResult, Component,
    ComponentInstallResult, ComponentRemovalResult, ComponentType, HealthCheckResult, HealthLevel,
    InstallationManifest, InstallKind, RollbackResult,
)
from agent_guidance.runtime import ProcessRunner, read_version

from .base import AgentAdapter
from .claude_plugins import ClaudePluginCli
from .codex import MCP_DIFFERENT_SETTINGS_REASON, AdapterError, _safe_name
from .json_support import (
    desired_json_mcp, install_git_skills, merge_mcp, read_json_object, remove_json_mcp,
    remove_managed_skills,
)
from agent_guidance.runtime import validate_managed_path


class ClaudeCodeAdapter(AgentAdapter):
    """User-scope Claude Code adapter based on the documented ~/.claude paths."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        # Plugins are installed through Claude Code's own marketplace commands, which have
        # inverses, so the transaction can reverse them.
        return AdapterCapabilities(
            skills=True, mcp=True, plugins=self.plugins.available, health_probe=False,
        )

    def __init__(self, home: Path | None = None, plugins: ClaudePluginCli | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        self.claude_home = self.home / ".claude"
        self.config_path = self.home / ".claude.json"
        self.settings_path = self.claude_home / "settings.json"
        self.skills_root = self.claude_home / "skills"
        self.plugins = plugins or ClaudePluginCli()

    def detect(self) -> AgentInstallation:
        executable = shutil.which("claude")
        version = None
        if executable:
            try:
                version = read_version(ProcessRunner().run([executable, "--version"], timeout=3).stdout)
            except (OSError, RuntimeError):
                pass
        detected = bool(executable or self.claude_home.exists() or self.config_path.exists())
        return AgentInstallation(
            agent=AgentType.CLAUDE_CODE, detected=detected,
            executable=Path(executable) if executable else None,
            config_path=self.config_path if self.config_path.exists() else None,
            version=version,
            details={"scope": "user", "settings": str(self.settings_path)},
        )

    def get_version(self) -> str | None:
        return self.detect().version

    def get_config_paths(self) -> list[Path]:
        return [self.config_path, self.settings_path]

    def list_existing_skills(self) -> list[str]:
        return sorted(path.parent.name for path in self.skills_root.glob("*/SKILL.md")) if self.skills_root.exists() else []

    def list_existing_mcps(self) -> list[str]:
        return sorted((read_json_object(self.config_path).get("mcpServers") or {}).keys())

    def list_existing_plugins(self) -> list[str]:
        """What Claude Code reports as installed, falling back to its settings.

        `enabledPlugins` records what is switched on, which is not the same as what is
        installed, so the CLI is asked first and the settings file is only a fallback for
        when it is unavailable.
        """
        try:
            return sorted(self.plugins.installed())
        except AdapterError:
            plugins = read_json_object(self.settings_path).get("enabledPlugins") or {}
            return sorted(plugins.keys()) if isinstance(plugins, dict) else []

    def inspect(self) -> dict[str, object]:
        skill_paths = sorted(path.parent for path in self.skills_root.glob("*/SKILL.md")) if self.skills_root.exists() else []
        return {
            "config_paths": self.get_config_paths(), "skills_root": self.skills_root,
            "skills": skill_paths, "mcp_servers": self.list_existing_mcps(),
            "plugins": self.list_existing_plugins(),
        }

    def existing_component_status(self, component: Component) -> tuple[bool, str | None]:
        if component.type == ComponentType.SKILL:
            # install_git_skills names directories with _safe_name, so the lookup must match it.
            prefix = f"{_safe_name(component.id)}--"
            exists = any(name.startswith(prefix) for name in self.list_existing_skills())
            return exists, "existing Claude Code Skill preserved" if exists else None
        if component.type == ComponentType.MCP:
            servers = read_json_object(self.config_path).get("mcpServers") or {}
            existing = servers.get(component.id) if isinstance(servers, dict) else None
            if existing == desired_json_mcp(component):
                return True, "compatible Claude Code MCP registration already exists"
            desired = desired_json_mcp(component)
            if isinstance(servers, dict) and any(
                value == desired for name, value in servers.items()
                if name.startswith(f"{component.id}-agent-guidance")
            ):
                return True, "compatible Agent Guidance MCP alias already exists"
            if existing is not None:
                return True, MCP_DIFFERENT_SETTINGS_REASON
        return False, None

    def backup(self, destination: Path) -> BackupManifest:
        destination.mkdir(parents=True, exist_ok=False)
        destination.chmod(0o700)
        entries: list[BackupEntry] = []
        for index, path in enumerate(self.get_config_paths()):
            entry = BackupEntry(original=path, existed=path.exists())
            if path.exists():
                target = destination / f"{index}-{path.name}"
                shutil.copy2(path, target)
                entry.backup = target
            entries.append(entry)
        return BackupManifest(root=destination, entries=entries)

    def install_skill(self, component: Component) -> ComponentInstallResult:
        return install_git_skills(component, self.skills_root)

    def configure_mcp(self, component: Component) -> ComponentInstallResult:
        return merge_mcp(self.config_path, component)

    def install_plugin(self, component: Component) -> ComponentInstallResult:
        """Add the marketplace if needed, install the plugin, and confirm it landed.

        Both steps are recorded so rollback reverses exactly what this run added: a
        marketplace the user already had is never removed, and a plugin already installed
        is preserved rather than reinstalled.
        """
        method = component.install_method
        if method.kind != InstallKind.PLUGIN_MARKETPLACE:
            raise AdapterError(
                f"Claude Code installs plugins from a marketplace, not {method.kind.value}: "
                "a Git URL alone has no manifest to validate and no inverse to roll back"
            )
        plugin_id = str(method.plugin_id)
        result = ComponentInstallResult(component_id=component.id)

        if plugin_id in self.plugins.installed():
            result.notes.append(f"plugin already installed and preserved: {plugin_id}")
            return result

        marketplace = str(method.marketplace)
        if marketplace not in self.plugins.marketplaces():
            if not method.marketplace_source:
                raise AdapterError(
                    f"marketplace '{marketplace}' is not known to Claude Code and the "
                    "component records no source to add it from"
                )
            added = self.plugins.add_marketplace(str(method.marketplace_source))
            result.added_marketplaces.append(added)
            if added != marketplace:
                result.notes.append(f"marketplace registered as '{added}'")
                plugin_id = f"{plugin_id.split('@', 1)[0]}@{added}"

        installed_id = self.plugins.install(plugin_id)
        if installed_id not in self.plugins.installed():
            raise AdapterError(
                f"Claude Code reported installing {installed_id} but does not list it as installed"
            )
        result.installed_plugins.append(installed_id)
        result.changed = True
        return result

    def remove_component(
        self,
        component: Component,
        paths: list[Path],
        file_hashes: dict[str, str],
        mcp_names: list[str],
        marketplaces: list[str],
    ) -> ComponentRemovalResult:
        result = ComponentRemovalResult(component_id=component.id)
        if component.type == ComponentType.SKILL:
            skills = remove_managed_skills(
                paths, self.skills_root, component.id, file_hashes,
            )
            result.owned_paths = skills.owned
            result.removed_paths.extend(skills.removed)
            result.preserved.extend(skills.preserved)
            result.errors.extend(skills.errors)
        elif component.type == ComponentType.MCP:
            try:
                removed_names, missing = remove_json_mcp(self.config_path, mcp_names)
                result.removed_mcp.extend(removed_names)
                result.preserved.extend(missing)
            except AdapterError as exc:
                result.errors.append(str(exc))
        elif component.type == ComponentType.PLUGIN:
            # Plugins come out before marketplaces, as in rollback: Claude Code will not
            # remove a marketplace while a plugin installed from it is still there.
            plugin_id = component.install_method.plugin_id
            if plugin_id:
                try:
                    if plugin_id in self.plugins.installed():
                        self.plugins.uninstall(plugin_id)
                        result.removed_plugins.append(plugin_id)
                    else:
                        result.preserved.append(f"{plugin_id}: not installed")
                except AdapterError as exc:
                    result.errors.append(f"{plugin_id}: {exc}")
            for marketplace in reversed(marketplaces):
                try:
                    self.plugins.remove_marketplace(marketplace)
                    result.removed_marketplaces.append(marketplace)
                except AdapterError as exc:
                    result.errors.append(f"marketplace {marketplace}: {exc}")
        result.changed = bool(
            result.removed_paths or result.removed_mcp
            or result.removed_plugins or result.removed_marketplaces
        )
        return result

    def health_check(self, expected: list[Component] | None = None, probe_mcp: bool = True) -> HealthCheckResult:
        del probe_mcp
        expected = expected or []
        detection = self.detect()
        checks = [CheckResult(
            name="claude_code_detected", passed=detection.detected,
            message="Claude Code executable or configuration detected" if detection.detected else "Claude Code was not detected",
        )]
        try:
            config = read_json_object(self.config_path)
            read_json_object(self.settings_path)
            checks.append(CheckResult(name="claude_config_parse", passed=True, message="Claude Code JSON is valid"))
        except AdapterError as exc:
            checks.append(CheckResult(name="claude_config_parse", passed=False, message=str(exc)))
            return HealthCheckResult(checks=checks)
        servers = config.get("mcpServers") or {}
        markers: set[str] = set()
        for marker in self.skills_root.glob("*/.agent-guidance-component.json") if self.skills_root.exists() else []:
            try:
                markers.add(json.loads(marker.read_text(encoding="utf-8"))["component_id"])
            except (OSError, ValueError, KeyError):
                pass
        expected_plugins = [item for item in expected if item.type == ComponentType.PLUGIN]
        if expected_plugins:
            try:
                installed = self.plugins.installed()
            except AdapterError as exc:
                installed = {}
                checks.append(CheckResult(
                    name="claude_plugin_cli", passed=False, fatal=False, message=str(exc),
                    level=HealthLevel.INITIALIZATION,
                ))
            for component in expected_plugins:
                plugin_id = str(component.install_method.plugin_id or component.id)
                entry = installed.get(plugin_id)
                checks.append(CheckResult(
                    name=f"claude_plugin_installed:{plugin_id}", passed=entry is not None,
                    message=(
                        f"plugin installed at {entry['installPath']}" if entry
                        else "plugin is not listed as installed"
                    ),
                ))
                if entry is not None:
                    checks.append(CheckResult(
                        name=f"claude_plugin_enabled:{plugin_id}",
                        passed=bool(entry.get("enabled")), fatal=False,
                        message=(
                            "plugin is enabled" if entry.get("enabled")
                            else "plugin is installed but switched off"
                        ),
                        level=HealthLevel.INITIALIZATION,
                    ))

        for component in expected:
            if component.type == ComponentType.SKILL:
                checks.append(CheckResult(
                    name=f"claude_skill_discovery:{component.id}", passed=component.id in markers,
                    message="Skill discovery metadata found" if component.id in markers else "Skill was not discoverable",
                    level=HealthLevel.INITIALIZATION,
                ))
            elif component.type == ComponentType.MCP:
                desired = desired_json_mcp(component)
                registered = next((value for value in servers.values() if value == desired), None) if isinstance(servers, dict) else None
                checks.append(CheckResult(
                    name=f"claude_mcp_config:{component.id}", passed=registered is not None,
                    message="MCP registration found" if registered is not None else "MCP registration missing",
                ))
                if registered and "url" in registered:
                    parsed = urlparse(str(registered["url"]))
                    checks.append(CheckResult(
                        name=f"claude_mcp_endpoint:{component.id}", passed=parsed.scheme == "https" and bool(parsed.netloc),
                        message="MCP HTTPS endpoint is valid",
                        level=HealthLevel.INITIALIZATION,
                    ))
                elif registered and "command" in registered:
                    available = shutil.which(str(registered["command"])) is not None
                    checks.append(CheckResult(
                        name=f"claude_mcp_process:{component.id}", passed=available,
                        message="MCP command is executable" if available else "MCP command not found",
                        level=HealthLevel.INITIALIZATION,
                    ))
        return HealthCheckResult(checks=checks)

    def rollback(self, manifest: InstallationManifest) -> RollbackResult:
        result = RollbackResult()
        # Plugins come out before marketplaces, since a marketplace cannot be removed while
        # a plugin installed from it is still there. Only what this run added is reversed.
        for plugin_id in reversed(manifest.installed_plugins):
            try:
                self.plugins.uninstall(plugin_id)
            except AdapterError as exc:
                result.errors.append(f"{plugin_id}: {exc}")
        for marketplace in reversed(manifest.added_marketplaces):
            try:
                self.plugins.remove_marketplace(marketplace)
            except AdapterError as exc:
                result.errors.append(f"marketplace {marketplace}: {exc}")
        allowed = self.skills_root.resolve()
        for path in reversed(manifest.created_paths):
            try:
                validate_managed_path(path, self.skills_root, allow_missing=False)
                resolved = path.resolve()
                if not resolved.is_relative_to(allowed) or not (resolved / ".agent-guidance-component.json").exists():
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
