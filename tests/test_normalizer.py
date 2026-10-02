from agent_guidance.models import (
    AgentType, Capability, ComponentType, InstallKind, MaintenanceStatus, SourceType,
)
from agent_guidance.sources.base import RawCandidate
from agent_guidance.sources.normalizer import normalize_candidate


def test_normalizes_repository_metadata_readme_structure_and_dependencies() -> None:
    raw = RawCandidate(
        repository_full_name="example/security-skill",
        repository_url="https://github.com/example/security-skill",
        source_type=SourceType.GITHUB,
        # GitHubSource sets source_version from pushed_at, so the realistic value here is a
        # timestamp. It is a cache key, never an install reference.
        source_version="2026-09-01T00:00:00Z",
        metadata={
            "name": "security-skill", "description": "Source code analysis and vulnerability research",
            "stargazers_count": 100, "forks_count": 5, "pushed_at": "2026-09-01T00:00:00Z",
            "license": {"spdx_id": "MIT"}, "head_sha": "abc123", "default_branch": "main",
        },
        readme="Codex security review skill. Install with Python.",
        tree_paths=["skills/a/SKILL.md", "pyproject.toml"],
        files={"skills/a/SKILL.md": "---\nname: a\ndescription: security\n---\n"},
    )
    component = normalize_candidate(raw)
    assert component.type == ComponentType.SKILL
    assert AgentType.CODEX in component.supported_agents
    assert Capability.SOURCE_ANALYSIS in component.capabilities
    assert component.install_method.kind == InstallKind.GIT_SKILLS
    assert component.install_method.ref == "abc123", "the head commit pins the install"
    assert component.maintenance_metadata.status == MaintenanceStatus.ACTIVE
    assert {item.name for item in component.dependencies} == {"Python"}
    assert component.evidence
