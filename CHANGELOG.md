# Changelog

## 0.1.0rc1 — 2026-09-30

### Added

- Codex, Claude Code, and Cursor adapters with multi-Agent planning.
- Deterministic interview, recommendation, conflict, security, reconciliation, and update flows.
- Explicit Adapter capabilities, transaction states, crash recovery, process lock, schema versions,
  component manifests, file hashes, and three-level Health Check data model.
- Linux, Windows, and macOS CI matrix plus packaging smoke checks.

### Changed

- Child processes now use one structured, timeout-bound, `shell=False` runner.
- Setup, update, and rollback serialize mutations with a stale-aware operation lock.
- Cache and state writes are atomic; future schemas are not rewritten.

### Security

- Added managed-root and symlink validation, secret redaction tests, immutable-ref metadata, and a
  documented threat/trust model.

### Known limitations

- Claude Code and Cursor do not yet have a functional MCP protocol probe.
- Update compares verified Registry refs rather than live upstream releases.
- WSL does not modify Windows-hosted Cursor configuration.
- Automated uninstall is not exposed.
