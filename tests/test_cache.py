from datetime import datetime, timedelta, timezone

from agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, SourceType, TrustMetadata,
)
from agent_guidance.sources.cache import CandidateCache


def component() -> Component:
    return Component(
        id="cached", name="Cached", type=ComponentType.SKILL,
        github_url="https://github.com/example/cached", supported_agents={AgentType.CODEX},
        capabilities={Capability.TESTING},
        trust=TrustMetadata(
            source_type=SourceType.GITHUB, verified=True, verification_reason="test",
        ),
    )


def test_cache_ttl_and_source_version(tmp_path, monkeypatch) -> None:
    secret = "ghp_cache_must_not_contain_this"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    path = tmp_path / "cache.json"
    cache = CandidateCache(path=path, ttl=timedelta(hours=1))
    cache.put(component(), "github", "v1")
    cache.save()
    assert secret not in path.read_text(encoding="utf-8")
    loaded = CandidateCache(path=path, ttl=timedelta(hours=1))
    assert loaded.get("https://github.com/example/cached", "v1") is not None
    assert loaded.get("https://github.com/example/cached", "v2") is None
    entry = next(iter(loaded.document.entries.values()))
    entry.fetched_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert loaded.get("https://github.com/example/cached", "v1") is None


def test_damaged_cache_is_ignored_with_warning(tmp_path) -> None:
    path = tmp_path / "cache.json"
    path.write_text("{partial", encoding="utf-8")
    cache = CandidateCache(path=path)
    assert cache.document.entries == {}
    assert cache.warnings and "damaged cache" in cache.warnings[0]
