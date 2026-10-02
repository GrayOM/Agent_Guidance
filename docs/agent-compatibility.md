# Agent Compatibility Evidence

Verified against official documentation on 2026-09-30.

| Agent | Skills | MCP | Plugins | GrayOM decision |
|---|---|---|---|---|
| Codex | [Agent Skills](https://developers.openai.com/codex/skills) | [`config.toml` MCP](https://developers.openai.com/codex/mcp) | No separate filesystem plugin install in scope | User Skill directory and TOML merge; Plugin capability false |
| Claude Code | [`~/.claude/skills/`](https://code.claude.com/docs/en/skills) | [User/project MCP](https://code.claude.com/docs/en/mcp) | [Marketplace-based plugins](https://code.claude.com/docs/en/plugins) | Skills and user MCP supported; Plugins installed through `claude plugin`, and only from a marketplace manifest |

Direct config merge is retained where the format and scope are documented because it permits exact backup,
atomic replacement, preservation checks, and rollback. Agent CLIs are used for read-only version detection;
GrayOM does not trade rollback guarantees for an opaque mutating CLI command.

Claude Code plugins are the one documented exception, and they are not an opaque command. Verified
against an installed Claude Code on 2026-10-02: `settings.json`'s `enabledPlugins` only toggles a
plugin that is already installed, while installing one registers a marketplace, fetches an archive,
validates its manifest, materialises it under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`
and may run a command the marketplace declares. Merging the settings file would therefore produce a
config entry pointing at nothing. Each CLI step reports `--json` and has an inverse that restores the
previous state exactly, so the delegation keeps the rollback guarantee rather than trading it:

| step | inverse |
|---|---|
| `claude plugin marketplace add <source> --scope user` | `claude plugin marketplace remove <name> --scope user` |
| `claude plugin install <plugin>@<marketplace> --scope user` | `claude plugin uninstall <plugin>@<marketplace> --scope user` |

`claude plugin install` also accepts `-y` / `--yes` and `--accept-command <sha256>`, which accept a
marketplace-declared command on the user's behalf. GrayOM never passes either, and refuses before the
process starts if one reaches the wrapper. A plugin that needs that approval is reported with the
command to run by hand.

Verified by installing a local marketplace into an isolated HOME and rolling it back: `uninstall`
and `marketplace remove` return `installed_plugins.json`, `known_marketplaces.json` and
`marketplaces/` to their previous contents, and `settings.json` to its previous state. Claude Code
keeps the extracted files under `plugins/cache/<marketplace>/<plugin>/<version>/` and marks them
`.orphaned_at` for its own collection; that path is outside GrayOM's managed root, so GrayOM leaves
it to Claude Code rather than deleting another tool's cache.
