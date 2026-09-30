# Release Candidate Audit — 0.1.0rc1

Audit date: 2026-09-30. `IMPLEMENTED` means code and an automated test or executable verification
exist. `PARTIAL` means the safe subset is implemented and the missing behavior is documented.

| Feature | Status | Evidence |
|---|---|---|
| Agent detection and version timeout | IMPLEMENTED | `adapters/*`, `runtime/process.py`, adapter tests |
| Work interview and deterministic recommendation | IMPLEMENTED | `cli/interview.py`, `core/recommender.py`, tests |
| Adapter capability filtering | IMPLEMENTED | `models/agent.py`, `core/multi_agent_plan.py`, RC tests |
| Cursor Plugin installation | MISSING | undocumented local-path write removed; capability is false until Marketplace/API integration |
| Config preservation | IMPLEMENTED | TOML comment-preserving merge; JSON semantic unknown-key preservation; fixtures and RC tests |
| Config formatting/comment preservation | PARTIAL | Codex TOML comments/order preserved; JSON has no standard comments and is normalized on write |
| Transaction lifecycle | IMPLEMENTED | explicit PREPARED through COMMITTED/ROLLED_BACK states and failure tests |
| Crash recovery | IMPLEMENTED | incomplete manifests are detected and rolled back before a new setup mutation |
| Cross-process lock | IMPLEMENTED | atomic lock creation, live PID rejection, stale lock recovery, tests |
| Path/symlink protection | IMPLEMENTED | shared path validator on backup/config/install targets and tests |
| Structured process execution | IMPLEMENTED | argument-list runner, `shell=False`, timeout, capture, redaction, tests |
| Immutable repository install | PARTIAL | configured refs are fetched detached; Registry entries without immutable refs remain unverified |
| Component manifests and hashes | IMPLEMENTED | per-component state manifests, source refs, paths and SHA-256 hashes |
| Safe uninstall | MISSING | no uninstall command is exposed; rollback removes manifest-owned paths only |
| Three-level Health Check | PARTIAL | status/level model exists; Codex has functional HTTP MCP probe; other adapters stop at static/initialization |
| Offline mode and damaged cache recovery | IMPLEMENTED | Registry/verified cache fallback, atomic cache writes, damaged cache warning state |
| Windows/macOS/Linux CI | IMPLEMENTED | GitHub Actions 3-OS × Python 3.11/3.12 matrix |
| Real installed-Agent OS test | NOT VERIFIED | CI uses isolated fixtures; no physical Windows/macOS Agent session was available |
| Packaging/clean install | IMPLEMENTED | wheel build, wheel reinstall, entry-point smoke in CI/release checks |
| Update | PARTIAL | verified Registry ref updates only; no live upstream version migration |

## Release blockers

The RC gate requires CI and clean-wheel checks to pass on the published commit. A final `0.1.0`
release must not be declared until the three-OS workflow has completed. Real Agent application
integration on Windows and macOS remains explicitly not verified and is a stable-release validation item.
