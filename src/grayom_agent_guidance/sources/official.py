from grayom_agent_guidance.models import AgentType, ComponentType, SourceType

from .base import RawCandidate, SourceUnavailable
from .github import GitHubSource


OFFICIAL_CATALOG = [
    {
        "repo": "github/github-mcp-server",
        "id": "github",
        "url": "https://github.com/github/github-mcp-server",
        "type": ComponentType.MCP,
        "agents": {AgentType.CODEX, AgentType.CLAUDE_CODE, AgentType.CURSOR},
        "reason": "Repository owned by GitHub and documented as the official GitHub MCP Server",
    },
    {
        "repo": "openai/skills",
        "id": "openai-skills",
        "url": "https://github.com/openai/skills",
        "type": ComponentType.SKILL,
        "agents": {AgentType.CODEX},
        "reason": "Repository owned by OpenAI and linked from official Codex Skill documentation",
    },
    {
        "repo": "anthropics/skills",
        "id": "anthropic-skills",
        "url": "https://github.com/anthropics/skills",
        "type": ComponentType.SKILL,
        "agents": {AgentType.CLAUDE_CODE},
        "reason": "Repository owned by Anthropic for Claude Agent Skills",
    },
]


class OfficialSource(GitHubSource):
    name = "official"

    def __init__(self, *args, selected_agents: set[AgentType] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.selected_agents = selected_agents or set()

    async def search(self, queries: list[str]) -> list[RawCandidate]:
        del queries
        rate = (await self._request("GET", "/rate_limit")).json().get("resources", {}).get("core", {})
        remaining = rate.get("remaining")
        if isinstance(remaining, int):
            self.rate_limit_remaining = remaining
        if remaining == 0:
            raise SourceUnavailable("GitHub core API rate limit exhausted")
        return [
            RawCandidate(
                component_id=item["id"], repository_full_name=item["repo"], repository_url=item["url"],
                source_type=SourceType.OFFICIAL, expected_type=item["type"],
                official_hint=True, verification_reason=item["reason"],
            )
            for item in OFFICIAL_CATALOG
            if not self.selected_agents or self.selected_agents & item["agents"]
        ]
