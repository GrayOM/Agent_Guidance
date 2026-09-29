import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from grayom_agent_guidance.models import Component
from grayom_agent_guidance.config import load_config


class CacheEntry(BaseModel):
    component: Component
    source: str
    fetched_at: datetime
    verified_at: datetime
    source_version: str | None = None


class CacheDocument(BaseModel):
    schema_version: int = 1
    entries: dict[str, CacheEntry] = Field(default_factory=dict)


class CandidateCache:
    def __init__(self, path: Path | None = None, ttl: timedelta | None = None) -> None:
        root = Path(os.environ.get("GRAYOM_HOME", Path.home() / ".grayom"))
        self.path = path or root / "cache" / "candidates.json"
        self.ttl = ttl or timedelta(hours=load_config().cache.ttl_hours)
        self.document = self._load()

    @staticmethod
    def key(repository_url: str) -> str:
        return repository_url.rstrip("/").lower()

    def _load(self) -> CacheDocument:
        if not self.path.exists():
            return CacheDocument()
        try:
            return CacheDocument.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return CacheDocument()

    def get(self, repository_url: str, source_version: str | None = None) -> Component | None:
        entry = self.document.entries.get(self.key(repository_url))
        if not entry:
            return None
        if datetime.now(timezone.utc) - entry.fetched_at > self.ttl:
            return None
        if source_version and entry.source_version and source_version != entry.source_version:
            return None
        return entry.component.model_copy(deep=True)

    def verified_components(self) -> list[Component]:
        return [
            entry.component.model_copy(deep=True)
            for entry in self.document.entries.values()
            if entry.component.trust.verified
        ]

    def put(self, component: Component, source: str, source_version: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        self.document.entries[self.key(str(component.github_url))] = CacheEntry(
            component=component, source=source, fetched_at=now, verified_at=now,
            source_version=source_version,
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(self.document.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
