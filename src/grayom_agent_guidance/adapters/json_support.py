import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from grayom_agent_guidance.core.skill_selection import SkillCandidate, select_skills
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


def skill_frontmatter(skill_file: Path) -> dict[str, Any]:
    content = skill_file.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if not content.startswith("---") or len(parts) < 3:
        raise AdapterError(f"invalid YAML frontmatter: {skill_file}")
    metadata = yaml.safe_load(parts[1]) or {}
    if not metadata.get("name") or not metadata.get("description"):
        raise AdapterError(f"Skill requires name and description: {skill_file}")
    return metadata


def clone_pinned(component: Component, destination: Path) -> Path:
    method = component.install_method
    repository = str(method.repository or component.github_url)
    if not repository.startswith("https://github.com/"):
        raise AdapterError("only HTTPS GitHub Skill repositories are supported")
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


def foreign_skill_names(skills_root: Path, component_id: str) -> set[str]:
    """Discoverable Skill names that this component does not own.

    A Skill this component installed earlier is the same Skill, not a collision. Counting
    it as one would make a repeated setup pick a different set every run, which is exactly
    what reinstalling is supposed to avoid. A Skill with no GrayOM marker is the user's own
    and always counts.
    """
    names: set[str] = set()
    if not skills_root.exists():
        return names
    for skill_file in skills_root.glob("*/SKILL.md"):
        marker = skill_file.parent / ".grayom-component.json"
        owner = None
        if marker.exists():
            try:
                owner = json.loads(marker.read_text(encoding="utf-8")).get("component_id")
            except (OSError, ValueError):
                owner = None
        if owner == component_id:
            continue
        try:
            names.add(str(skill_frontmatter(skill_file)["name"]))
        except (AdapterError, OSError, KeyError):
            continue
    return names


def install_git_skills(component: Component, skills_root: Path) -> ComponentInstallResult:
    """Install the Skills of a pinned repository that this run actually asked for.

    One implementation for every Agent: a repository holding dozens of Skills must be
    narrowed the same way whichever Agent it is being installed for.
    """
    method = component.install_method
    if method.kind != InstallKind.GIT_SKILLS:
        raise AdapterError(f"unsupported Skill install method: {method.kind}")
    result = ComponentInstallResult(component_id=component.id)
    skills_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="grayom-skill-") as temp_name:
        repo = clone_pinned(component, Path(temp_name))
        files = ([repo / subpath / "SKILL.md" for subpath in method.subpaths]
                 if method.subpaths else sorted(repo.rglob("SKILL.md")))
        files = [item for item in files if ".git" not in item.parts]
        if not files or any(not item.is_file() for item in files):
            raise AdapterError(f"no installable SKILL.md found for {component.id}")

        metadata_by_file = {item: skill_frontmatter(item) for item in files}
        chosen = _chosen_files(
            component, metadata_by_file, result,
            foreign_skill_names(skills_root, component.id),
        )

        for skill_file in chosen:
            metadata = metadata_by_file[skill_file]
            source = skill_file.parent
            if any(path.is_symlink() for path in source.rglob("*")):
                raise AdapterError(f"symlinks are not installed from external Skills: {source}")
            target = skills_root / f"{_safe_name(component.id)}--{_safe_name(str(metadata['name']))}"
            validate_managed_path(target, skills_root)
            if target.exists():
                result.preserved_paths.append(target)
                result.notes.append(f"preserved existing Skill: {target.name}")
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


def _chosen_files(
    component: Component,
    metadata_by_file: dict[Path, dict[str, Any]],
    result: ComponentInstallResult,
    existing_names: set[str] | None,
) -> list[Path]:
    """Apply the Plan's Skill selection policy, or install everything without one."""
    result.skills_available = len(metadata_by_file)
    policy = component.skill_selection
    if policy is None or not policy.capabilities:
        result.skills_selected = sorted(
            str(metadata["name"]) for metadata in metadata_by_file.values()
        )
        return list(metadata_by_file)

    by_name = {}
    candidates = []
    for skill_file, metadata in metadata_by_file.items():
        candidate = SkillCandidate(
            name=str(metadata["name"]), description=str(metadata["description"]),
            directory=str(skill_file.parent.name),
        )
        candidates.append(candidate)
        by_name.setdefault(candidate.name, skill_file)

    selection = select_skills(candidates, policy, existing_names=existing_names)
    result.skills_selected = selection.selected_names
    result.skills_skipped = selection.skipped_by_reason()
    if not selection.selected:
        result.notes.append(
            f"no Skill in this repository matches the selected work ({len(candidates)} available)"
        )
    return [by_name[name] for name in selection.selected_names]
