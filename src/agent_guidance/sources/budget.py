"""Request budget for live discovery.

GitHub enforces two independent limits, and an unauthenticated run is bounded by the
core limit long before the search limit:

| limit                | unauthenticated | authenticated |
|----------------------|-----------------|---------------|
| search API           | 10 per minute   | 30 per minute |
| core API (REST)      | 60 per hour     | 5000 per hour |

Fetching one repository costs ``FIXED_REQUESTS_PER_REPOSITORY`` core requests for its
metadata, README, head commit, latest release and tree, plus one per file whose contents
are read for security evidence. Discovery therefore has to size itself to the credentials
it actually has, instead of issuing a fixed number of requests and failing part-way with a
403 that silently degrades the recommendation to the local registry.
"""

import os

from pydantic import BaseModel, Field


FIXED_REQUESTS_PER_REPOSITORY = 5

SEARCH_LIMIT_PER_MINUTE = {False: 10, True: 30}
CORE_LIMIT_PER_HOUR = {False: 60, True: 5000}


class DiscoveryBudget(BaseModel):
    """How much live discovery a run can afford without exhausting a GitHub limit."""

    authenticated: bool
    search_queries_per_type: int = Field(ge=1)
    results_per_query: int = Field(ge=1)
    max_candidates: int = Field(ge=1)
    files_per_repository: int = Field(ge=0)
    official_repositories: int = Field(default=3, ge=0)

    @classmethod
    def detect(cls, *, authenticated: bool | None = None) -> "DiscoveryBudget":
        if authenticated is None:
            authenticated = bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        if authenticated:
            return cls(
                authenticated=True, search_queries_per_type=5, results_per_query=5,
                max_candidates=12, files_per_repository=16,
            )
        # 9 searches stay under 10/minute, and 5 repositories at 9 core requests each
        # stay under 60/hour with room for the rate-limit probes.
        return cls(
            authenticated=False, search_queries_per_type=3, results_per_query=3,
            max_candidates=2, files_per_repository=4,
        )

    @property
    def requests_per_repository(self) -> int:
        return FIXED_REQUESTS_PER_REPOSITORY + self.files_per_repository

    @property
    def search_requests(self) -> int:
        # One query per component type: Skill, MCP and Plugin.
        return self.search_queries_per_type * 3

    @property
    def core_requests(self) -> int:
        repositories = self.max_candidates + self.official_repositories
        return repositories * self.requests_per_repository

    @property
    def within_limits(self) -> bool:
        return (
            self.search_requests <= SEARCH_LIMIT_PER_MINUTE[self.authenticated]
            and self.core_requests <= CORE_LIMIT_PER_HOUR[self.authenticated]
        )

    def advisory(self) -> str | None:
        """A user-facing note when discovery is running narrower than it could."""
        if self.authenticated:
            return None
        return (
            "GitHub is being searched without a token, so discovery is limited to "
            f"{self.max_candidates} new repositories per run (GitHub allows "
            f"{CORE_LIMIT_PER_HOUR[False]} unauthenticated requests per hour). Set GITHUB_TOKEN "
            "or GH_TOKEN to search the full candidate set."
        )
