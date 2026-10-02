from datetime import datetime, timedelta, timezone

from agent_guidance.models import AgentType, CandidateState, MaintenanceStatus, SourceType
from agent_guidance.sources.base import RawCandidate
from agent_guidance.sources.normalizer import normalize_candidate
from agent_guidance.sources.validator import ComponentValidator


def raw_candidate(*, archived=False, pushed_at=None, readme="Codex vulnerability research skill"):
    return RawCandidate(
        repository_full_name="example/tool", repository_url="https://github.com/example/tool",
        source_type=SourceType.GITHUB,
        metadata={
            "name": "tool", "description": "vulnerability research", "archived": archived,
            "pushed_at": pushed_at, "license": None,
        },
        readme=readme, tree_paths=["SKILL.md"], source_version="abc",
    )


def test_archived_and_stale_candidates_are_warned_not_silently_blocked() -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=800)).isoformat()
    component = ComponentValidator({AgentType.CODEX}).validate(
        normalize_candidate(raw_candidate(archived=True, pushed_at=old))
    )
    assert component.recommendable
    assert component.maintenance_metadata.status == MaintenanceStatus.STALE
    assert "repository is archived" in component.validation_warnings
    assert "project appears stale" in component.validation_warnings


def test_unsupported_agent_is_sent_to_review() -> None:
    component = ComponentValidator({AgentType.CLAUDE_CODE}).validate(normalize_candidate(raw_candidate()))
    assert not component.recommendable
    assert component.candidate_state == CandidateState.REVIEW


def test_missing_readme_is_warned_not_silently_blocked() -> None:
    """A missing README is evidence quality, which the validator records as a warning.

    The candidate stays recommendable because its SKILL.md, capability and install method
    are all present; both thin-evidence notes travel with it to the Plan as limitations.
    """
    component = ComponentValidator({AgentType.CODEX}).validate(
        normalize_candidate(raw_candidate(readme=""))
    )
    assert component.recommendable
    assert any("README" in warning for warning in component.validation_warnings)
    assert any("SKILL.md format" in warning for warning in component.validation_warnings)
