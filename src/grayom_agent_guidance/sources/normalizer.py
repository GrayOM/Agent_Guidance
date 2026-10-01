import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import PurePosixPath

from grayom_agent_guidance.models import (
    AgentType, CandidateState, Capability, Component, ComponentType,
    DependencyRequirement, EvidenceItem, InstallKind, InstallMethod,
    MaintenanceMetadata, MaintenanceStatus, Permission, TrustMetadata,
)

from .base import RawCandidate
from .repository_security import scan_repository


CAPABILITY_KEYWORDS: dict[Capability, tuple[str, ...]] = {
    Capability.SECURITY_ANALYSIS: ("security analysis", "security review", "sast", "audit"),
    Capability.SOURCE_ANALYSIS: ("source code analysis", "code analysis", "static analysis"),
    Capability.VULNERABILITY_RESEARCH: (
        "vulnerability", "vulnerabilities", "cve", "exploit research",
    ),
    Capability.AI_VULNERABILITY_ANALYSIS: ("llm security", "ai security", "prompt injection"),
    Capability.REPOSITORY_ACCESS: (
        "repository", "repositories", "github", "pull request", "issues",
    ),
    Capability.TESTING: ("testing", "test automation", "pytest"),
    Capability.TEST_EXECUTION: ("test runner", "run tests", "jest", "vitest"),
    Capability.CODE_EDITING: ("code editing", "coding agent", "implementation"),
    Capability.CODE_REVIEW: ("code review", "pull request review"),
    Capability.REFACTORING: ("refactor",),
    Capability.DEBUGGING: ("debugging", "debugger", "stack trace", "breakpoint"),
    Capability.PLANNING: ("planning", "task breakdown", "roadmap", "task decomposition"),
    Capability.DEVELOPMENT_WORKFLOW: ("development workflow", "developer workflow", "git workflow"),
    Capability.DEPENDENCY_MANAGEMENT: (
        "dependency", "dependencies", "package manager", "lockfile", "sbom",
    ),
    Capability.API_INTEGRATION: ("api client", "rest api", "openapi", "graphql"),
    Capability.CI_CD: ("ci/cd", "continuous integration", "continuous delivery", "github actions"),
    Capability.CONTAINERIZATION: ("docker", "containeriz", "container image", "podman"),
    Capability.ORCHESTRATION: ("kubernetes", "k8s", "helm", "kubectl"),
    Capability.INFRASTRUCTURE_AS_CODE: (
        "terraform", "infrastructure as code", "pulumi", "cloudformation", "ansible",
    ),
    Capability.OBSERVABILITY: (
        "observability", "monitoring", "prometheus", "grafana", "opentelemetry", "tracing",
    ),
    Capability.CLOUD_PLATFORM: ("aws", "azure", "google cloud", "gcp", "cloudflare"),
    Capability.MOBILE_IOS: ("ios", "swiftui", "swift package", "xcode"),
    Capability.MOBILE_ANDROID: ("android", "jetpack compose", "kotlin", "gradle"),
    Capability.CROSS_PLATFORM: ("react native", "flutter", "expo", "capacitor"),
    Capability.DATA_ANALYSIS: ("data analysis", "analytics"),
    Capability.DATABASE_ACCESS: ("database", "postgres", "mysql", "sqlite", "sql query"),
    Capability.DATA_PIPELINE: ("etl", "data pipeline", "airflow", "dbt"),
    Capability.DATA_VISUALIZATION: ("data visualization", "chart", "dashboard", "plotting"),
    Capability.BROWSER_AUTOMATION: ("browser automation", "playwright", "browser agent"),
    Capability.NETWORK_ACCESS: ("osint", "reconnaissance", "network access"),
    Capability.WEB_RESEARCH: ("web search", "web research", "scraping", "crawler"),
    Capability.DOCUMENT_AUTHORING: ("document generation", "markdown", "docx", "technical writing"),
    Capability.KNOWLEDGE_MANAGEMENT: ("knowledge base", "notion", "obsidian", "note-taking"),
    Capability.REPORTING: ("reporting", "report generation", "documentation"),
    Capability.AGENT_DEVELOPMENT: ("agent development", "multi-agent", "rag agent"),
}


def mentions(text: str, keywords: tuple[str, ...]) -> bool:
    """Match a keyword at a word start.

    Anchoring only the start still matches a grown suffix, so "audit" covers "auditing",
    while a short token can no longer match inside an unrelated word: a plain substring test
    tagged every repository mentioning "studios" or "radios" as iOS.

    It does not cover a spelling change, so a keyword ending in -y lists its -ies plural
    explicitly rather than relying on the anchor.
    """
    return any(re.search(rf"\b{re.escape(keyword)}", text) for keyword in keywords)


def _maintenance(metadata: dict) -> MaintenanceMetadata:
    pushed_at = metadata.get("pushed_at") or metadata.get("updated_at")
    status = MaintenanceStatus.UNKNOWN
    if pushed_at:
        try:
            updated = datetime.fromisoformat(str(pushed_at).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated).days
            status = MaintenanceStatus.ACTIVE if age <= 365 else MaintenanceStatus.STALE
        except ValueError:
            pass
    license_data = metadata.get("license") or {}
    license_name = license_data.get("spdx_id") if isinstance(license_data, dict) else license_data
    return MaintenanceMetadata(
        status=status,
        license=license_name if license_name not in {"NOASSERTION", "Other"} else None,
        stars=metadata.get("stargazers_count"), forks=metadata.get("forks_count"),
        last_commit=pushed_at, latest_release=metadata.get("latest_release"),
        archived=bool(metadata.get("archived", False)),
        issue_activity=(
            f"{metadata.get('open_issues_count')} open issues"
            if metadata.get("open_issues_count") is not None else None
        ),
        release_activity=metadata.get("latest_release"),
    )


def _component_id(raw: RawCandidate) -> str:
    if raw.component_id:
        return raw.component_id
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw.repository_full_name.lower().replace("/", "-"))
    slug = slug.strip("-.")[:128]
    if not slug or not re.match(r"^[a-z0-9]", slug):
        raise ValueError(f"repository name cannot form a safe component id: {raw.repository_full_name}")
    return slug


def _component_type(raw: RawCandidate, text: str) -> ComponentType:
    if raw.expected_type:
        return raw.expected_type
    lowered_paths = [path.lower() for path in raw.tree_paths]
    # A plugin manifest only outranks SKILL.md when it sits at a documented plugin location;
    # an incidental plugin.json must not reclassify a Skill repository.
    if any(path.endswith(".codex-plugin/plugin.json") for path in lowered_paths):
        return ComponentType.PLUGIN
    if any(path.endswith("skill.md") for path in lowered_paths):
        return ComponentType.SKILL
    if any(path.endswith("plugin.json") for path in lowered_paths):
        return ComponentType.PLUGIN
    if any("mcp" in PurePosixPath(path).name.lower() for path in lowered_paths) or "mcp server" in text or "model context protocol" in text:
        return ComponentType.MCP
    raise ValueError("repository structure does not identify a Skill, MCP, or Plugin")


# Codex and Claude Code both consume the same SKILL.md format from their own user
# Skill directory, which docs/agent-compatibility.md records per Agent.
SKILL_FORMAT_AGENTS = frozenset({AgentType.CODEX, AgentType.CLAUDE_CODE})

SKILL_FORMAT_NOTE = (
    "no Agent is named in the repository, so Skill support is inferred from the shared "
    "SKILL.md format rather than from an Agent-specific statement"
)


def _supported_agents(
    text: str, paths: list[str], component_type: ComponentType,
) -> tuple[set[AgentType], str | None]:
    joined = text + " " + " ".join(paths).lower()
    result = set()
    if "codex" in joined or ".agents/skills" in joined:
        result.add(AgentType.CODEX)
    if "claude code" in joined or ".claude" in joined:
        result.add(AgentType.CLAUDE_CODE)
    if result or component_type != ComponentType.SKILL:
        return result, None
    # A community SKILL.md that never names an Agent is still installable by all three,
    # and dropping it would discard most third-party Skills.
    return set(SKILL_FORMAT_AGENTS), SKILL_FORMAT_NOTE


def _dependencies(raw: RawCandidate) -> list[DependencyRequirement]:
    paths = {path.lower() for path in raw.tree_paths}
    readme = (raw.readme or "").lower()
    requirements: list[DependencyRequirement] = []
    definitions = [
        ("Node.js", "node", any(path.endswith("package.json") for path in paths) or "npx " in readme),
        ("Python", "python", any(path.endswith(("pyproject.toml", "requirements.txt")) for path in paths)),
        ("uv", "uv", " uv " in f" {readme} " or any(path.endswith("uv.lock") for path in paths)),
        ("Docker", "docker", any(PurePosixPath(path).name.lower() == "dockerfile" for path in paths) or "docker run" in readme),
    ]
    for name, executable, required in definitions:
        if required:
            requirements.append(DependencyRequirement(
                name=name, executable=executable, detected=shutil.which(executable) is not None,
                evidence="repository structure or README",
            ))
    return requirements


def _install_ref(raw: RawCandidate) -> str | None:
    """A ref git can resolve.

    source_version carries the repository's pushed_at timestamp, which is a cache key rather
    than a reference, so it must never become one: `git fetch origin 2026-01-01T00:00:00Z`
    cannot resolve. The head commit is preferred because it pins the install.
    """
    return raw.metadata.get("head_sha") or raw.metadata.get("default_branch")


def _install_method(raw: RawCandidate, component_type: ComponentType) -> InstallMethod:
    if component_type == ComponentType.SKILL:
        return InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository=raw.repository_url,
            ref=_install_ref(raw),
        )
    if component_type == ComponentType.PLUGIN:
        return InstallMethod(
            kind=InstallKind.PLUGIN_GIT, repository=raw.repository_url,
            ref=_install_ref(raw),
        )
    readme = raw.readme or ""
    urls = re.findall(r"https://[^\s)`\"']+/mcp/?", readme, flags=re.I)
    if urls:
        return InstallMethod(kind=InstallKind.MCP_HTTP, url=urls[0].rstrip(".,"))
    npx = re.search(r"\bnpx\s+(?:-y\s+)?([@\w./-]+)([^\n`]*)", readme)
    if npx:
        args = ["-y", npx.group(1)] + [item for item in npx.group(2).strip().split() if not item.startswith("$")]
        return InstallMethod(kind=InstallKind.MCP_STDIO, command="npx", args=args[:12])
    return InstallMethod()


def normalize_candidate(raw: RawCandidate) -> Component:
    readme = raw.readme or ""
    text = f"{raw.metadata.get('description') or ''}\n{readme}".lower()
    component_type = _component_type(raw, text)
    capabilities = {
        capability for capability, keywords in CAPABILITY_KEYWORDS.items()
        if mentions(text, keywords)
    }
    agents, agent_inference_note = _supported_agents(text, raw.tree_paths, component_type)
    security = scan_repository({"README.md": readme, **raw.files})
    maintenance = _maintenance(raw.metadata)
    official = raw.official_hint
    trust = TrustMetadata(
        source_type=raw.source_type, official=official,
        verified=bool(official and raw.verification_reason),
        verification_reason=raw.verification_reason or "GitHub repository metadata and contents",
    )
    evidence = list(security.evidence)
    evidence.extend([
        EvidenceItem(field="readme_present", value=bool(readme.strip()), source="GitHub contents"),
        EvidenceItem(field="component_type", value=component_type.value, source="repository_structure"),
        EvidenceItem(
            field="supported_agents", value=sorted(agent.value for agent in agents),
            source="SKILL.md format" if agent_inference_note else "README/repository_structure",
            location=agent_inference_note,
        ),
        EvidenceItem(field="maintenance", value=maintenance.status.value, source="GitHub metadata"),
    ])
    stars = maintenance.stars or 0
    quality = min(95, 45 + (10 if readme else 0) + (10 if maintenance.license else 0) + int(math.log10(stars + 1) * 6))
    permissions = set()
    if security.metadata.network_access:
        permissions.add(Permission.NETWORK)
    if security.metadata.shell_execution:
        permissions.add(Permission.SHELL)
    if security.metadata.subprocess:
        permissions.add(Permission.SUBPROCESS)
    if security.metadata.filesystem_delete:
        permissions.add(Permission.FILESYSTEM_DELETE)
    if security.metadata.credential_access:
        permissions.add(Permission.CREDENTIALS)
    dependencies = _dependencies(raw)
    install_method = _install_method(raw, component_type)
    evidence.append(EvidenceItem(
        field="install_method", value=install_method.kind.value,
        source="README/repository_structure",
    ))
    return Component(
        id=_component_id(raw),
        name=raw.metadata.get("name") or raw.repository_full_name.split("/")[-1],
        type=component_type, source=raw.source_type.value, repository_url=raw.repository_url,
        official=official, supported_agents=agents, capabilities=capabilities,
        permissions=permissions, context_cost=3, quality_score=quality,
        install_method=install_method, security_metadata=security.metadata,
        maintenance_metadata=maintenance, trust=trust, evidence=evidence,
        dependencies=dependencies, candidate_state=CandidateState.DISCOVERED,
        validation_warnings=(
            security.warnings + [agent_inference_note] if agent_inference_note
            else security.warnings
        ),
        install_complexity=min(5, 1 + len(dependencies)),
    )
