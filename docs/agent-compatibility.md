# Agent Compatibility Evidence

Verified against official documentation on 2026-09-30.

| Agent | Skills | MCP | Plugins | GrayOM decision |
|---|---|---|---|---|
| Codex | [Agent Skills](https://developers.openai.com/codex/skills) | [`config.toml` MCP](https://developers.openai.com/codex/mcp) | No separate filesystem plugin install in scope | User Skill directory and TOML merge; Plugin capability false |
| Claude Code | [`~/.claude/skills/`](https://code.claude.com/docs/en/skills) | [User/project MCP](https://code.claude.com/docs/en/mcp) | [Marketplace-based plugins](https://code.claude.com/docs/en/plugins) | Skills and user MCP supported; arbitrary Git Plugin install disabled |

Direct config merge is retained where the format and scope are documented because it permits exact backup,
atomic replacement, preservation checks, and rollback. Agent CLIs are used for read-only version detection;
GrayOM does not trade rollback guarantees for an opaque mutating CLI command.
