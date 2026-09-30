import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import tomlkit
import yaml

from grayom_agent_guidance.models import (
    AdapterCapabilities, AgentInstallation, AgentType, BackupEntry, BackupManifest, CheckResult, Component,
    ComponentInstallResult, ComponentType, HealthCheckResult, HealthLevel, InstallationManifest,
    InstallKind, RollbackResult,
)
from grayom_agent_guidance.runtime import ProcessRunner, validate_managed_path

from .base import AgentAdapter


class AdapterError(RuntimeError):
    pass


class ExistingConfigurationConflict(AdapterError):
    pass


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower()).strip("-.")
    if not normalized or normalized in {".", ".."}:
        raise AdapterError(f"unsafe component name: {value!r}")
    return normalized


class CodexAdapter(AgentAdapter):
    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(skills=True, mcp=True, plugins=False, health_probe=True)

    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        configured_home = os.environ.get("CODEX_HOME") if home is None else None
        self.codex_home = Path(configured_home).expanduser().resolve() if configured_home else self.home / ".codex"
        self.config_path = self.codex_home / "config.toml"
        self.skills_root = self.home / ".agents" / "skills"

    def detect(self) -> AgentInstallation:
        executable = shutil.which("codex")
        detected = bool(executable or self.codex_home.exists())
        version = None
        if executable:
            try:
                version = ProcessRunner().run([executable, "--version"], timeout=3).stdout.strip() or None
            except (OSError, RuntimeError):
                pass
        return AgentInstallation(
            agent=AgentType.CODEX, detected=detected,
            executable=Path(executable) if executable else None,
            config_path=self.config_path if self.config_path.exists() else None,
            version=version,
        )

    def get_version(self) -> str | None:
        return self.detect().version

    def get_config_paths(self) -> list[Path]:
        return [self.config_path]

    def list_existing_skills(self) -> list[str]:
        return [path.parent.name for path in self.skills_root.glob("*/SKILL.md")] if self.skills_root.exists() else []

    def list_existing_mcps(self) -> list[str]:
        return sorted((self._read_config().get("mcp_servers") or {}).keys())

    def list_existing_plugins(self) -> list[str]:
        return []

    def _read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("rb") as stream:
            return tomllib.load(stream)

    def inspect(self) -> dict[str, object]:
        config = self._read_config()
        skills = []
        if self.skills_root.exists():
            skills = sorted(path.parent for path in self.skills_root.glob("*/SKILL.md"))
        return {
            "codex_home": self.codex_home,
            "config_exists": self.config_path.exists(),
            "skills_root": self.skills_root,
            "skills": skills,
            "mcp_servers": sorted((config.get("mcp_servers") or {}).keys()),
            "plugins": [],
        }

    def existing_component_status(self, component: Component) -> tuple[bool, str | None]:
        """Return whether an existing component must be preserved instead of changed."""
        if component.type == ComponentType.SKILL:
            prefix = f"{_safe_name(component.id)}--"
            exists = any(name.startswith(prefix) for name in self.list_existing_skills())
            return exists, "existing Codex Skill preserved" if exists else None
        if component.type != ComponentType.MCP:
            return False, None
        server = (self._read_config().get("mcp_servers") or {}).get(component.id)
        if server is None:
            return False, None
        desired = self._desired_mcp(component)
        if "url" in desired:
            compatible = server.get("url") == desired["url"]
        else:
            compatible = (
                server.get("command") == desired.get("command")
                and list(server.get("args", [])) == list(desired.get("args", []))
            )
        if compatible:
            return True, "compatible MCP registration already exists; preserved"
        if any(dict(value) == desired for name, value in (self._read_config().get("mcp_servers") or {}).items() if name.startswith(f"{component.id}-grayom")):
            return True, "compatible GrayOM MCP alias already exists; preserved"
        return True, "MCP id already exists with different settings; a safe GrayOM alias will be used"

    def backup(self, destination: Path) -> BackupManifest:
        destination.mkdir(parents=True, exist_ok=False)
        destination.chmod(0o700)
        entry = BackupEntry(original=self.config_path, existed=self.config_path.exists())
        if self.config_path.exists():
            target = destination / "config.toml"
            shutil.copy2(self.config_path, target)
            entry.backup = target
        return BackupManifest(root=destination, entries=[entry])

    def _clone_pinned(self, component: Component, destination: Path) -> Path:
        method = component.install_method
        repository = str(method.repository or component.github_url)
        if not repository.startswith("https://github.com/"):
            raise AdapterError("MVP only installs Skills from HTTPS GitHub repositories")
        repo = destination / "repo"
        commands = [
            ["git", "init", "--quiet", str(repo)],
            ["git", "-C", str(repo), "remote", "add", "origin", repository],
            ["git", "-C", str(repo), "fetch", "--quiet", "--depth", "1", "origin", method.ref or "HEAD"],
            ["git", "-C", str(repo), "checkout", "--quiet", "--detach", "FETCH_HEAD"],
        ]
        for command in commands:
            try:
                ProcessRunner().run(command, check=True, timeout=60)
            except FileNotFoundError as exc:
                raise AdapterError("git executable is required for Skill installation") from exc
            except RuntimeError as exc:
                raise AdapterError(str(exc)) from exc
        return repo

    @staticmethod
    def _skill_metadata(skill_file: Path) -> dict[str, Any]:
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise AdapterError(f"missing YAML frontmatter: {skill_file}")
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise AdapterError(f"invalid YAML frontmatter: {skill_file}")
        metadata = yaml.safe_load(parts[1]) or {}
        if not metadata.get("name") or not metadata.get("description"):
            raise AdapterError(f"Skill requires name and description: {skill_file}")
        return metadata

    @staticmethod
    def _reject_symlinks(root: Path) -> None:
        if any(path.is_symlink() for path in root.rglob("*")):
            raise AdapterError(f"symlinks are not installed from external Skills: {root}")

    def install_skill(self, component: Component) -> ComponentInstallResult:
        if component.install_method.kind != InstallKind.GIT_SKILLS:
            raise AdapterError(f"unsupported Skill install method: {component.install_method.kind}")
        result = ComponentInstallResult(component_id=component.id)
        self.skills_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="grayom-skill-") as temp_name:
            repository = self._clone_pinned(component, Path(temp_name))
            if component.install_method.subpaths:
                skill_files = [repository / subpath / "SKILL.md" for subpath in component.install_method.subpaths]
            else:
                skill_files = sorted(repository.rglob("SKILL.md"))
            skill_files = [path for path in skill_files if ".git" not in path.parts]
            if not skill_files or any(not path.is_file() for path in skill_files):
                raise AdapterError(f"no installable SKILL.md found for {component.id}")
            for skill_file in skill_files:
                metadata = self._skill_metadata(skill_file)
                source_dir = skill_file.parent
                self._reject_symlinks(source_dir)
                suffix = _safe_name(str(metadata["name"]))
                target = self.skills_root / f"{_safe_name(component.id)}--{suffix}"
                validate_managed_path(target, self.skills_root)
                if target.exists():
                    result.preserved_paths.append(target)
                    result.notes.append(f"preserved existing Skill: {target.name}")
                    continue
                staging = self.skills_root / f".grayom-{uuid4().hex}"
                shutil.copytree(source_dir, staging, ignore=shutil.ignore_patterns(".git", "__pycache__"))
                marker = {
                    "component_id": component.id,
                    "source": str(component.github_url),
                    "ref": component.install_method.ref,
                    "skill_name": metadata["name"],
                }
                (staging / ".grayom-component.json").write_text(
                    json.dumps(marker, indent=2), encoding="utf-8",
                )
                os.replace(staging, target)
                result.created_paths.append(target)
                result.changed = True
        return result

    def _desired_mcp(self, component: Component) -> dict[str, Any]:
        method = component.install_method
        if method.kind == InstallKind.MCP_HTTP:
            desired: dict[str, Any] = {"url": str(method.url)}
            if method.bearer_token_env_var:
                desired["bearer_token_env_var"] = method.bearer_token_env_var
        elif method.kind == InstallKind.MCP_STDIO:
            desired = {"command": method.command}
            if method.args:
                desired["args"] = method.args
            if method.env:
                desired["env"] = method.env
            if method.env_vars:
                desired["env_vars"] = method.env_vars
        else:
            raise AdapterError(f"unsupported MCP install method: {method.kind}")
        desired["startup_timeout_sec"] = method.startup_timeout_sec
        return desired

    def configure_mcp(self, component: Component) -> ComponentInstallResult:
        desired = self._desired_mcp(component)
        result = ComponentInstallResult(component_id=component.id)
        self.codex_home.mkdir(parents=True, exist_ok=True)
        original = self.config_path.read_text(encoding="utf-8") if self.config_path.exists() else ""
        try:
            document = tomlkit.parse(original)
        except Exception as exc:
            raise AdapterError(f"existing Codex config is invalid TOML: {exc}") from exc
        servers = document.get("mcp_servers")
        if servers is None:
            servers = tomlkit.table()
            document.add("mcp_servers", servers)
        registration_name = component.id
        existing = servers.get(registration_name)
        if existing is not None:
            existing_plain = dict(existing)
            if "url" in desired:
                identity_matches = existing_plain.get("url") == desired["url"]
            else:
                identity_matches = (
                    existing_plain.get("command") == desired.get("command")
                    and list(existing_plain.get("args", [])) == list(desired.get("args", []))
                )
            if identity_matches:
                result.notes.append("compatible MCP registration already exists and was preserved")
                result.configured_mcp.append(component.id)
                return result
            base = f"{component.id}-grayom"
            registration_name = base
            suffix = 2
            while servers.get(registration_name) is not None:
                candidate = dict(servers[registration_name])
                if candidate == desired:
                    result.configured_mcp.append(registration_name)
                    result.notes.append(f"compatible MCP alias already exists: {registration_name}")
                    return result
                registration_name = f"{base}-{suffix}"
                suffix += 1
            result.notes.append(
                f"preserved conflicting MCP '{component.id}' and registered '{registration_name}'"
            )
        server = tomlkit.table()
        for key, value in desired.items():
            server.add(key, value)
        servers.add(registration_name, server)
        rendered = tomlkit.dumps(document)
        temporary = self.config_path.with_name(f"config.toml.grayom-{uuid4().hex}.tmp")
        validate_managed_path(self.config_path, self.codex_home)
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(rendered)
                stream.flush()
                os.fsync(stream.fileno())
            with temporary.open("rb") as stream:
                tomllib.load(stream)
            os.replace(temporary, self.config_path)
        finally:
            temporary.unlink(missing_ok=True)
        result.changed = True
        result.configured_mcp.append(registration_name)
        return result

    def install_plugin(self, component: Component) -> ComponentInstallResult:
        raise AdapterError("Codex Plugin installation is intentionally outside this MVP")

    @staticmethod
    def _parse_mcp_response(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            raise AdapterError("MCP server returned no SSE data")
        return response.json()

    def _probe_http_mcp(self, server_id: str, config: dict[str, Any]) -> tuple[bool, str]:
        token_name = config.get("bearer_token_env_var")
        if token_name and not os.environ.get(token_name):
            return False, f"authentication environment variable is not set: {token_name}"
        headers = {"Accept": "application/json, text/event-stream"}
        if token_name:
            headers["Authorization"] = f"Bearer {os.environ[token_name]}"
        initialize = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "grayom-agent-guidance", "version": "0.1.0"},
            },
        }
        try:
            with httpx.Client(timeout=5, follow_redirects=True, headers=headers) as client:
                response = client.post(str(config["url"]), json=initialize)
                response.raise_for_status()
                initialized = self._parse_mcp_response(response)
                if initialized.get("error"):
                    return False, f"initialize error: {initialized['error']}"
                session = response.headers.get("mcp-session-id")
                tool_headers = {"mcp-session-id": session} if session else {}
                client.post(
                    str(config["url"]), headers=tool_headers,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
                tool_response = client.post(
                    str(config["url"]), headers=tool_headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                )
                tool_response.raise_for_status()
                tools = self._parse_mcp_response(tool_response).get("result", {}).get("tools", [])
                return bool(tools), f"discovered {len(tools)} tools"
        except (httpx.HTTPError, ValueError, AdapterError) as exc:
            return False, f"MCP probe failed: {exc}"

    def _skill_checks(self, expected_ids: set[str]) -> list[CheckResult]:
        checks: list[CheckResult] = []
        names: dict[str, Path] = {}
        discovered_ids: set[str] = set()
        if self.skills_root.exists():
            for skill_file in self.skills_root.glob("*/SKILL.md"):
                try:
                    metadata = self._skill_metadata(skill_file)
                    name = str(metadata["name"])
                    if name in names:
                        checks.append(CheckResult(
                            name=f"skill_duplicate:{name}", passed=False, fatal=False,
                            message=f"duplicate Skill name in {names[name]} and {skill_file}",
                            level=HealthLevel.INITIALIZATION,
                        ))
                    names[name] = skill_file
                    marker = skill_file.parent / ".grayom-component.json"
                    if marker.exists():
                        discovered_ids.add(json.loads(marker.read_text(encoding="utf-8"))["component_id"])
                except (AdapterError, OSError, ValueError, KeyError) as exc:
                    marker = skill_file.parent / ".grayom-component.json"
                    managed_expected = False
                    if marker.exists():
                        try:
                            managed_expected = json.loads(marker.read_text(encoding="utf-8")).get(
                                "component_id"
                            ) in expected_ids
                        except (OSError, ValueError):
                            pass
                    checks.append(CheckResult(
                        name=f"skill_parse:{skill_file.parent.name}", passed=False, fatal=managed_expected,
                        message=str(exc), level=HealthLevel.INITIALIZATION,
                    ))
        for component_id in expected_ids:
            checks.append(CheckResult(
                name=f"skill_discovery:{component_id}", passed=component_id in discovered_ids,
                message="Skill discovery metadata found" if component_id in discovered_ids
                else "installed Skill was not discoverable",
                level=HealthLevel.INITIALIZATION,
            ))
        return checks

    def health_check(
        self, expected: list[Component] | None = None, probe_mcp: bool = True,
    ) -> HealthCheckResult:
        expected = expected or []
        detection = self.detect()
        checks = [CheckResult(
            name="codex_detected", passed=detection.detected,
            message="Codex executable or home directory detected" if detection.detected
            else "Codex was not detected",
        )]
        try:
            config = self._read_config()
            checks.append(CheckResult(name="config_parse", passed=True, message="config.toml is valid"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            checks.append(CheckResult(name="config_parse", passed=False, message=str(exc)))
            return HealthCheckResult(checks=checks)

        expected_skills = {item.id for item in expected if item.type == ComponentType.SKILL}
        checks.extend(self._skill_checks(expected_skills))
        servers = config.get("mcp_servers") or {}
        expected_mcp = [item for item in expected if item.type == ComponentType.MCP]
        for component in expected_mcp:
            server = servers.get(component.id)
            if server is None:
                desired = self._desired_mcp(component)
                server = next((value for value in servers.values() if dict(value) == desired), None)
            checks.append(CheckResult(
                name=f"mcp_config:{component.id}", passed=server is not None,
                message="MCP registration found" if server is not None else "MCP registration missing",
            ))
            if not server:
                continue
            if "command" in server:
                command_ok = shutil.which(str(server["command"])) is not None
                checks.append(CheckResult(
                    name=f"mcp_process:{component.id}", passed=command_ok,
                    message="MCP command is executable" if command_ok else "MCP command was not found",
                    level=HealthLevel.INITIALIZATION,
                ))
            elif "url" in server:
                parsed = urlparse(str(server["url"]))
                url_ok = parsed.scheme == "https" and bool(parsed.netloc)
                checks.append(CheckResult(
                    name=f"mcp_url:{component.id}", passed=url_ok,
                    message="MCP HTTPS endpoint is valid" if url_ok else "MCP endpoint is not valid HTTPS",
                    level=HealthLevel.INITIALIZATION,
                ))
                if probe_mcp and url_ok:
                    passed, message = self._probe_http_mcp(component.id, server)
                    checks.append(CheckResult(
                        name=f"mcp_tool_discovery:{component.id}", passed=passed, fatal=False,
                        message=message, level=HealthLevel.FUNCTIONAL,
                    ))
        return HealthCheckResult(checks=checks)

    def rollback(self, manifest: InstallationManifest) -> RollbackResult:
        result = RollbackResult()
        allowed_root = self.skills_root.resolve()
        for path in reversed(manifest.created_paths):
            try:
                validate_managed_path(path, self.skills_root, allow_missing=False)
                resolved = path.resolve()
                if not resolved.is_relative_to(allowed_root):
                    raise AdapterError(f"refusing to remove path outside managed Skill root: {resolved}")
                marker = resolved / ".grayom-component.json"
                if not marker.exists():
                    raise AdapterError(f"refusing to remove unmarked existing path: {resolved}")
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
