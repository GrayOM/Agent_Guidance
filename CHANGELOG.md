# Changelog

## Unreleased

### Added

- Claude Code Plugin installation, delegated to `claude plugin` and wrapped in a GrayOM
  transaction. Each step has an inverse (`marketplace add`/`remove`, `install`/`uninstall`), the
  manifest records only what the run added, and rollback removes plugins before marketplaces.
- GitHub discovery reads `.claude-plugin/marketplace.json` and builds a `<plugin>@<marketplace>`
  install id from the live manifest. Manifests are read before the per-repository file budget runs
  out, so an anonymous run still learns whether a repository is installable.
- Health Check reports a Claude Code plugin's installed state as fatal and its enabled state as a
  warning, because a plugin that is installed but switched off is not a failed install.
- Agent multi-select keeps a candidate that supports at least one selected Agent, and names the
  Agents it will not be applied to.
- Capability-bucketed GitHub discovery: one query became 9–15, candidates are interleaved per
  capability instead of ranked globally by stars, and request volume is sized to the credentials
  present.
- Skill auto-selection with a per-mode limit, name-collision and redundancy rules, and a one-line
  summary of what was installed.
- Live upstream comparison on `update`, with unchecked reported separately from unchanged.
- A curated set of six first-party Claude Code plugins from Anthropic's own
  `claude-code-plugins` marketplace, each read from the live manifest. Verified against
  Claude Code 2.1.287: adding `anthropics/claude-code` registers the marketplace under the
  name `claude-code-plugins`, which is why the install id cannot be derived from the
  repository name.

### Changed

- Claude Code's Plugin capability now follows whether its CLI is present, rather than being
  hard-coded false.
- A repository that ships `SKILL.md` stays a Skill candidate even when it also publishes a
  marketplace, so its Skills are selected rather than bundled in wholesale.
- GitHub 401, 429 and plain 403 are reported as the different problems they are, and one refusal
  that stopped every repository is reported once.
- Support is limited to Codex and Claude Code; the Cursor adapter was removed.

### Fixed

- One part of a Skill repository can no longer take the whole Skill budget. Measured on
  `trailofbits/skills`: `building-secure-contracts` held 7 of 12 Performance slots with six
  per-platform scanners that are one job described six times; it now holds 4, and the
  repository groups represented go from 6 to 8.
- A repository's own test fixtures are no longer installable Skills. Two of the 85 SKILL.md
  files in `trailofbits/skills` live under `tests/fixtures/`, and one ranked 19th for a
  security request.
- The first-run screenshot no longer carries the empty row left by removing Cursor.
- A second `setup` run no longer installs a different set of Skills: a component's own Skills are
  no longer counted as a foreign name collision.
- `SKILL.md`-only repositories are recognised, so community Skills are no longer discarded.
- Install refs are a commit or branch, never the `pushed_at` timestamp used as a cache key.

## 0.1.0rc1 — 2026-09-30

### Added

- Codex and Claude Code adapters with multi-Agent planning.
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

- Claude Code does not yet have a functional MCP protocol probe.
- Update compares verified Registry refs rather than live upstream releases.
- WSL does not modify a Windows-hosted Agent's configuration.
- Automated uninstall is not exposed.
