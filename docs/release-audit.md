# Release Audit — 0.1.0

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
| Safe uninstall | IMPLEMENTED | `grayom uninstall` works from state, so it reaches a component installed long before the last transaction; it refuses an EXISTING component, a Skill directory whose files no longer hash to what was installed, and any MCP name GrayOM did not record writing; `core/uninstall.py` with 13 tests and an executed run on real Codex and Claude Code |
| Three-level Health Check | PARTIAL | Codex's functional probe was executed on 2026-10-02 against the real CLI and correctly reported L3 `WARN mcp_tool_discovery:github: authentication environment variable is not set`; Claude Code stops at L2 (static and initialization), so no functional probe exists for it |
| Offline mode and damaged cache recovery | IMPLEMENTED | Registry/verified cache fallback, atomic cache writes, damaged cache warning state |
| Windows/macOS/Linux CI | IMPLEMENTED | GitHub Actions 3-OS × Python 3.11/3.12 matrix |
| Real installed-Agent OS test | IMPLEMENTED | Verified 2026-10-02 on Linux, Windows and macOS against real Codex 0.160.0 and Claude Code 2.1.287 installed from npm, by the `real-agents` CI job running `scripts/real_agent_check.py`: detection, install for both Agents, health including Codex's L3 probe, state record, uninstall, and a check that nothing of GrayOM's is left. Its first run failed on Windows and macOS and found a real cross-platform defect, which is the evidence that the job tests something Linux could not |
| Packaging/clean install | IMPLEMENTED | wheel build, wheel reinstall, entry-point smoke in CI/release checks |
| Update | IMPLEMENTED | `cli/main.py` resolves upstream live through `resolve_upstream_refs` and reports unchecked components separately from unchanged ones; the Registry is the fallback when upstream cannot be reached. It reinstalls at the new ref rather than migrating state across versions, which is the stated behaviour, not a gap |

The three dashes this audit used to carry for untested platforms are gone, and the row above says so
because a job executed it rather than because the claim was reworded.

## Release gate result

`0.1.0`: **READY**. The Ubuntu, Windows and macOS matrix passes on Python 3.11/3.12 alongside quality,
dependency-audit and clean-wheel packaging checks, and a `real-agents` job now installs Codex and
Claude Code on all three platforms and drives detect, install, health, uninstall and verify against
them.

This is an RC decision, not a claim that final `0.1.0` is fully field-validated. Two things are still
outside what has been executed anywhere:

- **Live GitHub discovery.** Every end-to-end run so far was made in a container whose GitHub access
  is restricted to this repository, so the Registry and verified-cache paths are exercised and the
  live search path is not. GrayOM reports that refusal correctly — as an access decision rather than
  a rate limit — but the path itself is unverified.
- **Uninstalling a component the user has edited.** The directory is preserved on purpose and the
  component stays recorded, so removing it is still the user's own job. That is the safe behaviour,
  not a bug, but it does mean `uninstall` is not guaranteed to leave nothing behind.
