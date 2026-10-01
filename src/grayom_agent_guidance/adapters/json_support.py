import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from grayom_agent_guidance.models import Component, ComponentInstallResult, InstallKind
from grayom_agent_guidance.runtime import ProcessRunner, validate_managed_path

from .codex import AdapterError, _safe_name


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"invalid JSON configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError(f"JSON configuration must be an object: {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    validate_managed_path(path, path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.grayom-{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        read_json_object(temporary)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def desired_json_mcp(component: Component) -> dict[str, Any]:
    """The MCP registration Claude Code's documented `mcpServers` object expects."""
    method = component.install_method
    if method.kind == InstallKind.MCP_HTTP:
        desired: dict[str, Any] = {"url": str(method.url), "type": "http"}
        if method.bearer_token_env_var:
            desired["headers"] = {
                "Authorization": f"Bearer ${{{method.bearer_token_env_var}}}"
            }
    elif method.kind == InstallKind.MCP_STDIO:
        desired = {"command": method.command, "type": "stdio"}
        if method.args:
            desired["args"] = list(method.args)
        if method.env:
            desired["env"] = dict(method.env)
    else:
        raise AdapterError(f"unsupported MCP install method: {method.kind}")
    return desired


def merge_mcp(path: Path, component: Component) -> ComponentInstallResult:
    document = read_json_object(path)
    servers = document.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise AdapterError(f"mcpServers must be an object in {path}")
    desired = desired_json_mcp(component)
    result = ComponentInstallResult(component_id=component.id)
    name = component.id
    if name in servers:
        if servers[name] == desired:
            result.configured_mcp.append(name)
            result.notes.append("compatible MCP registration already exists and was preserved")
            return result
        base = f"{component.id}-grayom"
        name = base
        suffix = 2
        while name in servers:
            if servers[name] == desired:
                result.configured_mcp.append(name)
                result.notes.append(f"compatible MCP alias already exists: {name}")
                return result
            name = f"{base}-{suffix}"
            suffix += 1
        result.notes.append(f"preserved conflicting MCP '{component.id}' and registered '{name}'")
    servers[name] = desired
    atomic_write_json(path, document)
    result.changed = True
    result.configured_mcp.append(name)
    return result


def install_git_skills(component: Component, skills_root: Path) -> ComponentInstallResult:
    method = component.install_method
    if method.kind != InstallKind.GIT_SKILLS:
        raise AdapterError(f"unsupported Skill install method: {method.kind}")
    repository = str(method.repository or component.github_url)
    if not repository.startswith("https://github.com/"):
        raise AdapterError("only HTTPS GitHub Skill repositories are supported")
    result = ComponentInstallResult(component_id=component.id)
    skills_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="grayom-skill-") as temp_name:
        repo = Path(temp_name) / "repo"
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
        files = ([repo / subpath / "SKILL.md" for subpath in method.subpaths]
                 if method.subpaths else sorted(repo.rglob("SKILL.md")))
        files = [item for item in files if ".git" not in item.parts]
        if not files or any(not item.is_file() for item in files):
            raise AdapterError(f"no installable SKILL.md found for {component.id}")
        for skill_file in files:
            content = skill_file.read_text(encoding="utf-8")
            if not content.startswith("---") or len(content.split("---", 2)) < 3:
                raise AdapterError(f"invalid YAML frontmatter: {skill_file}")
            metadata = yaml.safe_load(content.split("---", 2)[1]) or {}
            if not metadata.get("name") or not metadata.get("description"):
                raise AdapterError(f"Skill requires name and description: {skill_file}")
            source = skill_file.parent
            if any(path.is_symlink() for path in source.rglob("*")):
                raise AdapterError(f"symlinks are not installed from external Skills: {source}")
            target = skills_root / f"{_safe_name(component.id)}--{_safe_name(str(metadata['name']))}"
            validate_managed_path(target, skills_root)
            if target.exists():
                result.preserved_paths.append(target)
                continue
            staging = skills_root / f".grayom-{uuid4().hex}"
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            atomic_write_json(staging / ".grayom-component.json", {
                "component_id": component.id, "source": str(component.github_url),
                "ref": method.ref, "skill_name": metadata["name"],
            })
            os.replace(staging, target)
            result.created_paths.append(target)
            result.changed = True
    return result
