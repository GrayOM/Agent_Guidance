# Release Candidate Audit — 0.1.0rc1

Audit date: 2026-09-30, re-verified 2026-10-02. `IMPLEMENTED` means code and an automated test or
executable verification exist. `PARTIAL` means the safe subset is implemented and the missing
behavior is documented.

The 2026-10-02 pass was prompted by a direct question about what had actually been run rather than
asserted. It found two rows stating less than the code does — Update had been implemented and the
row never updated, and the Linux Agent session had since been verified — and one row claiming more
than was true, since the interview prompts had no coverage at all. Each row below now names what was
executed.

| Feature | Status | Evidence |
|---|---|---|
| Agent detection and version timeout | IMPLEMENTED | `adapters/*`, `runtime/process.py`, adapter tests |
| Work interview and deterministic recommendation | IMPLEMENTED | `cli/interview.py` at 100% line coverage: the prompts run for real against scripted keystrokes, and the interview's own order, per-domain task questions and both refusals run against a recorder |
| Adapter capability filtering | IMPLEMENTED | `models/agent.py`, `core/multi_agent_plan.py`, RC tests |
| Plugin installation | IMPLEMENTED | Claude Code plugins delegated to `claude plugin` with an inverse per step, marketplace-only install methods, and plugin tests; verified end to end against the real CLI, installing `code-review@claude-code-plugins` and rolling it back; Codex capability stays false |
| Config preservation | IMPLEMENTED | TOML comment-preserving merge; JSON semantic unknown-key preservation; fixtures and RC tests; verified 2026-10-02 against a real `~/.codex/config.toml` carrying comments, `model`, `approval_policy`, a `[tui]` section and the user's own MCP server, all preserved after a merge |
| Config formatting/comment preservation | PARTIAL | Codex TOML comments/order preserved; JSON has no standard comments and is normalized on write |
| Transaction lifecycle | IMPLEMENTED | explicit PREPARED through COMMITTED/ROLLED_BACK states and failure tests |
| Crash recovery | IMPLEMENTED | incomplete manifests are detected and rolled back before a new setup mutation |
| Cross-process lock | IMPLEMENTED | atomic lock creation, live PID rejection, stale lock recovery, tests |
| Path/symlink protection | IMPLEMENTED | shared path validator on backup/config/install targets and tests |
| Structured process execution | IMPLEMENTED | argument-list runner, `shell=False`, timeout, capture, redaction, tests |
| Immutable repository install | PARTIAL | configured refs are fetched detached; Registry entries without immutable refs remain unverified |
| Component manifests and hashes | IMPLEMENTED | per-component state manifests, source refs, paths and SHA-256 hashes |
| Safe uninstall | MISSING | no uninstall command is exposed; rollback removes manifest-owned paths only |
| Three-level Health Check | PARTIAL | Codex's functional probe was executed on 2026-10-02 against the real CLI and correctly reported L3 `WARN mcp_tool_discovery:github: authentication environment variable is not set`; Claude Code stops at L2 (static and initialization), so no functional probe exists for it |
| Offline mode and damaged cache recovery | IMPLEMENTED | Registry/verified cache fallback, atomic cache writes, damaged cache warning state |
| Windows/macOS/Linux CI | IMPLEMENTED | GitHub Actions 3-OS × Python 3.11/3.12 matrix |
| Real installed-Agent OS test | PARTIAL | Linux verified 2026-10-02 against real Codex 0.160.0 and Claude Code 2.1.287: dual-Agent detection, install for both, health including Codex's L3 probe, state record, and rollback restoring both Agents to their prior state. Windows and macOS remain NOT VERIFIED — CI there uses isolated fixtures and no physical Agent session was available |
| Packaging/clean install | IMPLEMENTED | wheel build, wheel reinstall, entry-point smoke in CI/release checks |
| Update | IMPLEMENTED | `cli/main.py` resolves upstream live through `resolve_upstream_refs` and reports unchecked components separately from unchanged ones; the Registry is the fallback when upstream cannot be reached. It reinstalls at the new ref rather than migrating state across versions, which is the stated behaviour, not a gap |

## Release gate result

`0.1.0rc1`: **READY**. GitHub Actions run 36652076601 passed the Ubuntu, Windows, and macOS matrix on
Python 3.11/3.12 plus quality, dependency-audit, and clean-wheel packaging checks, and the matrix has
passed on every merge since.

This is an RC decision, not a claim that final `0.1.0` is fully field-validated. Two things are still
outside what has been executed anywhere:

- Real installed-Agent application sessions on **Windows and macOS**. Linux is now covered against
  both real CLIs; the other two platforms run CI against isolated fixtures only.
- **Live GitHub discovery.** Every end-to-end run so far was made in a container whose GitHub access
  is restricted to this repository, so the Registry and verified-cache paths are exercised and the
  live search path is not. GrayOM reports that refusal correctly — as an access decision rather than
  a rate limit — but the path itself is unverified.
