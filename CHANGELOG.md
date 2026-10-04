# Changelog

## 0.2.0 — 2026-10-04

Everything below came out of the first runs on a machine that was not this project's. Live
GitHub discovery ran for the first time, and what it returned found four defects that no test
had covered, three of them about the same thing: a README is the repository owner's own text,
and this program had been reading it as fact.

### Added

- The release workflow can publish to PyPI, through Trusted Publishing: PyPI is told which
  repository, which workflow file and which environment may publish this project, and the job
  proves it with a short-lived OIDC token minted for that one run. No API token is created,
  stored as a secret or printed anywhere, so there is none to leak or rotate. Until the
  publisher is configured on PyPI the job fails and nothing is published, and the `pypi`
  environment can carry a required reviewer, so an irreversible action waits for a person.

- The published description rewrites README.md's relative paths to absolute ones. The file
  refers to its screenshots and the other documents by relative path, which is right in a
  checkout and broken on PyPI: published as-is the project page would have carried eight
  broken images — the logo and every screenshot — and five links that 404. The file itself is
  unchanged, and a test applies the configured rewrite to the real README so a screenshot
  added later with a relative path fails in CI rather than on a page nobody checks.

- `scripts/real_agent_check.py` now seeds its throwaway HOME with hand-written Agent
  configuration — a comment, an option set by hand, an MCP server registered by hand with its
  own args and environment — and checks all of it survived the install, then that both
  uninstall and rollback restore the files byte for byte. Every end-to-end run before this
  started from an empty HOME, so the README's promise to anyone with an existing setup had
  never been exercised; the run also asserts that the install wrote to those files at all,
  because under the previous answer it recommended Skills only, left `config.toml` untouched,
  and every preservation check passed without the merge code running once.

- `agent-guidance self-check`, which checks that the program does what it was designed to do
  on the machine running it and prints what each of six claims measured. It installs nothing
  and writes nothing outside a temporary directory.

### Security

- A discovered HTTP MCP server was registered against the wrong URL. On a real run the GitHub
  MCP Server was written into both Agent configs as
  `url = "https://insiders.vscode.dev/redirect/mcp/"` — Microsoft's editor-install redirect,
  not an MCP endpoint — carrying `bearer_token_env_var = "GITHUB_PAT_TOKEN"`, so the user's
  GitHub token was configured to be sent to a host nobody chose. Nothing was exfiltrated,
  because of whose host it happens to be; the shape is a credential going somewhere
  unintended.

  Two defects met there. The pattern reading an endpoint out of a README matched a *prefix* of
  a longer URL, so the two "Install in VS Code" badges at the top of that README read as
  endpoints and the first one won; the endpoint the project actually serves is the fourth
  match. `/mcp` now has to end the URL, badge and documentation hosts are not endpoints
  whatever order they appear in, and among what is left the most frequently written URL wins,
  because a README repeats its endpoint through its examples and mentions an aside once.

  And the built-in registry declares that endpoint correctly, but the merge preferred the
  scraped URL because the official source outranks the registry — then kept the registry's
  bearer token. A declared install method now beats a scraped one whatever the sources rank:
  source rank says which description of a project to prefer, not that a README is more
  authoritative than a declared install method. The README is kept as a test fixture, because
  the ordering is the defect and a sample written from memory would put the endpoint first
  and pass.

- A discovered MCP server's launch command was read out of its repository's README and written
  to the user's Agent configuration unexamined. Three things met there. The npm package name
  was never checked against the repository it was advertised under, so a README under one
  project could install anyone's package. Nothing was pinned: `npx -y name` resolves npm's
  current latest every time the Agent starts the server, so a package that is clean when it is
  installed is not necessarily the package that runs next week, even though Skills from the
  same search are pinned to `head_sha`. And the risk review had no rule for either, so the
  approval screen showed nothing and the candidate was labelled verified.

  Such a server is now resolved against the npm registry before it is offered. The package has
  to exist, it has to declare the repository it was discovered from, and the install is pinned
  to the exact version the registry reports — the README's own `@latest` included. A package
  that cannot be resolved is not recommended, and the reason says which of the three it was.
  This is the counterpart of the rule Plugins already had, which MCP did not.

  The registry lookup uses its own HTTP client. Reusing the GitHub one would have sent the
  user's `GITHUB_TOKEN` to npmjs.org, which would have been worse than the problem being
  fixed; a test asserts the request carries no credentials.

- The risk review now reports a launch command that came from a README, and the version an
  install is pinned to. A Skill that falls back to a branch name because the commit lookup did
  not land is reported too, as a warning rather than a refusal: that fallback exists for
  anonymous rate limits, and dropping the candidate would shrink the result set for a reason
  that has nothing to do with the repository.

### Fixed

- `tests/test_version.py` asserted `__version__ == "0.1.0"`, so every release broke it and the
  fix was to edit the number — a test that only confirms someone typed the same thing twice.
  It now asserts the version and the newest changelog section agree, which is the invariant
  the release workflow depends on. The `--version` test reads the running version for the same
  reason.

- Recommendations ranked a sprawling README above a focused one, because the first sort key
  counted how many needed capabilities a component claims and a capability is inferred from a
  README, so claiming one is free. Measured on a real run where the user asked for web and
  AI-Agent development:

      component                  claims  covers  precision  README
      samugit83-redamon              25       7       0.28  101,752 chars  <- 1st
      aquaticat-monochromatic        14       5       0.36   13,287 chars  <- 2nd
      superpowers                     5       4       0.80                <- 3rd
      github (official)               3       2       0.67                <- 4th

  First place went to an autonomous exploitation framework claiming 25 of the 37 capabilities
  that exist, which installed 1 of its 15 Skills because that was all that matched; second to
  a 148-package monorepo. Coverage is now weighted by precision — the share of what a
  component claims that is actually wanted — which puts the focused Skill set first. Coverage
  still separates two equally focused candidates, and a broad project is still selected when
  nothing focused covers a capability, which is how that same run still reached it second.

- A Skill made an MCP server redundant. The coverage bookkeeping was keyed by Agent and
  capability with no component type, so selecting a Skill that mentions code review dropped
  the official GitHub MCP server as adding nothing — a Skill is written instructions the Agent
  reads and an MCP server is tools it can call, and `_duplicate_of` already refused to compare
  across types. The official server had survived only by being ordered first, and fixing the
  ranking above exposed it.

- `agent-guidance uninstall` did not put a Codex config back to the byte. Removing an MCP
  table leaves the blank line that separated it behind, so a `config.toml` that ended in one
  newline came back from an uninstall ending in two. Trailing whitespace carries no meaning in
  TOML, but "uninstall puts your config back" is a promise about the file. The file's own
  trailing newlines are now restored rather than normalised to one: a config kept without a
  final newline stays that way, because tidying it is still editing someone's file for reasons
  they did not ask for.

- A `self-check` run that reached GitHub but was refused the repositories it named reported
  two failures and exit 1. An anonymous run gets 60 requests an hour, so a second run inside
  that hour reaches the search endpoint, is told about repositories, and is then denied every
  one of them — and the claims that read the candidate list found it empty. That is the claim
  untested, not the program broken, which is the same distinction the `checked` flag already
  drew one step earlier. `SourceResult` now counts the repositories it could not read, and
  both claims report unproven with GitHub's own words and the remedy. Discovering nothing that
  installs code reports unproven too, rather than passing vacuously or failing.

- The `self-check` pinning claim asserted that *some* discovered candidate was pinned, so a run
  with three of four pinned printed PASS and listed the three. The gap was invisible, and one
  pin in a hundred would have read the same way. It now counts how many of how many, names the
  ones that are not pinned and what they resolved to instead, and fails when any candidate on
  offer is unpinned.

- The design check ran as a script from a clone, and a clone that has not been installed has
  the package on `sys.path` without any of its dependencies. The first person to run it got
  `ModuleNotFoundError: tomlkit` out of the middle of an adapter: a stack trace that reads as
  a broken program and means nothing was installed. The check now lives in the package, where
  a command can only run in an environment that has the dependencies, and
  `scripts/design_check.py` answers a missing install with the command to run instead of a
  traceback. `scripts/real_agent_check.py` carried the same trap and now answers the same way.

## 0.1.0 — 2026-10-02

The first release. Every feature in `architecture.md` is implemented, and the audit's own gaps
are closed or named rather than quietly dropped.

Two are named. A component whose files the user has edited after installation is preserved
rather than removed, which is deliberate: the program does not delete work it did not write.
It says which directory it left and where. And live GitHub discovery has never been run
against `api.github.com` end to end, because the machines available to this project cannot
reach its search endpoint; everything from the HTTP response through normalisation,
validation and recommendation is exercised against a repository object captured from the real
API, which leaves the socket call itself as the only unexercised step.

### Added

- `agent-guidance uninstall`, which removes what Agent Guidance installed and refuses to remove anything
  else. It works from state rather than from a transaction manifest, so a component can be
  removed long after the run that installed it — which `rollback` could never do. Three
  refusals carry the safety, each reported rather than silently narrowing the work: a
  component that was already there is not Agent Guidance's, a Skill directory whose files no longer
  hash to what was installed stays with the user, and an MCP registration Agent Guidance did not
  write is never deleted. `--agent` removes for one Agent and leaves the other's install
  intact; `--dry-run` shows the plan without touching anything.
- State records the MCP registration names and marketplaces Agent Guidance actually wrote, per
  Agent. Without them an uninstall would have to guess, and an MCP can land under `<id>`,
  `<id>-agent-guidance` or `<id>-agent-guidance-2` depending on what the user already had — so the guess
  would eventually delete someone's own server.
- `scripts/real_agent_check.py` and a `real-agents` CI job on Linux, Windows and macOS. It
  installs the Agents themselves and drives detect, install, health, uninstall and verify
  against them for real, in a throwaway HOME and with no credentials. The same command runs
  on a user's own machine. Its first run failed on Windows and macOS and found a real
  cross-platform defect, which closes the audit's longest-standing gap with evidence rather
  than with a rewording.

- A `penetration_testing` work domain for assessing a target someone else built and
  deployed, with thirteen engagement-phase questions (web application, authentication,
  authorisation, injection, API, mobile, secure code review, infrastructure, configuration,
  cloud configuration, reproduction, reporting, retest). It carries two new capabilities:
  `web_security_testing`, because `security_analysis` and `source_analysis` both surface
  SAST tooling, which is the wrong tool class for a deployed application the user did not
  write; and `configuration_audit`, because a checklist review against a baseline reaches
  neither of those vocabularies. All eleven domains still produce distinct profiles.
- Skill selection gives every requested capability the repository can cover a slot before
  filling the rest by rank, scarcest capability first.
- Curated Skill paths on the three Registry Skill entries, read one by one at their pinned
  refs: 17 of 83 for `trailofbits-skills`, 12 of 15 for `superpowers`, 24 of 25 for
  `addy-agent-skills`. Measured on the assessment and CVE profiles: platform-specific
  scanners and tool-dependent Skills went from 5 of 12 Performance slots to none, with
  capability coverage unchanged at 7/7 and 5/5.
- A curated path upstream has moved or dropped is reported and skipped instead of failing
  the install, because `update` reinstalls at a newer ref carrying the same paths. Curated
  paths are resolved inside the clone only.
- Claude Code Plugin installation, delegated to `claude plugin` and wrapped in a Agent Guidance
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

- Written labels for all 11 work domains and 78 tasks, with a guard test. The interview
  derived its labels from the identifiers, so the only screen a user interacts with offered
  "Osint Recon", "Ci Cd Pipeline", "Ios App" and "Ai Llm Security"; no capitalisation rule
  recovers an acronym from a snake_case key, so each label is now written out and a new task
  fails the suite until it gets one.
- `scripts/capture_screens.py`, which produces every screenshot in the README by running the
  real CLI. The interview is an InquirerPy prompt, so each screen is driven through a pty with
  scripted keystrokes and read back from a VT100 emulator; `--check` re-captures and fails when
  a committed image no longer matches the program.
- `tests/test_assets.py`, which parses every SVG in `docs/assets` with a strict XML parser and
  names the double-hyphen-in-a-comment case directly. A rendered screenshot shows how a file
  looks; it does not show that the file is well formed, and only the second kind of check
  catches a file a browser renders and a strict parser refuses.
- `tests/test_github_real_payload.py` and `tests/fixtures/github_repository.json`: a repository
  object captured verbatim from the GitHub API, with its volatile counters pinned. The other
  GitHub tests write their responses by hand, so they prove the code works against the fields
  those tests chose to include; this one runs search, paging, normalisation, validation and
  recommendation against all 95 real fields.
- `python -m agent_guidance`, for a source checkout or an unactivated virtualenv where the
  `agent-guidance` script is not on PATH.

### Changed

- Claude Code's Plugin capability now follows whether its CLI is present, rather than being
  hard-coded false.
- A repository that ships `SKILL.md` stays a Skill candidate even when it also publishes a
  marketplace, so its Skills are selected rather than bundled in wholesale.
- GitHub 401, 429 and plain 403 are reported as the different problems they are, and one refusal
  that stopped every repository is reported once.
- Support is limited to Codex and Claude Code; the Cursor adapter was removed.

- `agent-guidance --help` is two panels, "Everyday use" and "When something goes wrong",
  instead of one flat list of seven commands that made all seven look equally necessary. Every
  description is written for someone who has just installed this.
- `--probe-mcp/--no-probe-mcp` and `setup --dry-run` are hidden from help. The first is
  internal and weakens the health check when turned off; the second duplicates
  `agent-guidance recommend`, which says what it does in its name. Both still work for scripts.
- The menu offers every command it should. `uninstall` was reachable only by typing it, so the
  menu could install but not undo. Each entry now says what choosing it does.
- `agent-guidance uninstall` names the directory it leaves behind and says to delete it by
  hand. The note read "changed since install", which said what happened without saying where
  to look.
- The README is a walkthrough built on the captured screenshots: one command, what each screen
  asks, and what the plan tells you before you approve it.

### Fixed

- Installing a Skill repository no longer fails when the clone root is not its own real
  path. A Windows short 8.3 TEMP (`RUNNER~1`) and its long form (`runneradmin`) name the
  same directory without being prefixes of one another, and macOS puts the temporary
  directory under `/var`, a symlink to `/private/var`; either made `relative_to` raise and
  the whole install fail. Linux hid it, and the new real-Agent CI job surfaced it on both
  other platforms on its first run.
- The interview prompts are covered. `cli/interview.py` went from 30% to 100%: the real
  prompts run against scripted keystrokes, and the interview's own order, per-domain task
  questions and both refusals run against a recorder. Nothing had executed that code —
  every test and every end-to-end run called `build_answer` with a scripted answer, so the
  screens a user actually answers had no verification that they render at all.
- `docs/release-audit.md` matches the code again. Two rows understated it (Update had been
  implemented and the row never updated; the Linux Agent session had since been verified)
  and one overstated it (the interview claimed test evidence it did not have).
- A capability is no longer reported as covered while nothing providing it is installed.
  Measured on `trailofbits/skills` at its pinned ref: a web application assessment profile
  reported `web_security_testing` covered — correctly, the repository carries
  `burpsuite-project-parser` — and then installed six other Skills, because that one ranked
  below the limit. The assessment profile now covers 8 of 8 reachable capabilities.
- `trailofbits-skills` declares `web_security_testing`, verified against the pinned commit
  rather than the default branch. The `configuration_audit` claim added alongside it is
  withdrawn: it rested on `firebase-apk-scanner`, and scanning an APK for Firebase
  misconfigurations is not the baseline review of servers, network gear and databases the
  question asks about — the same over-reach the coverage fix was meant to end. Nothing in
  that repository covers it, and it now reads as uncovered.
- Two plugins published by one marketplace repository are two candidates again. Candidate
  merging keyed on the repository, so the six curated plugins from
  `github.com/anthropics/claude-code` collapsed into a single candidate carrying one
  plugin's name, another's id, a third's install method and the union of everyone's
  capabilities — a component that does not exist, recommended with a reason listing
  capabilities it does not have. A marketplace plugin is now identified by its install id.
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

- The detected-Agents line reads `Codex (0.160.0)` and `Claude Code (2.1.287)`. Both adapters
  stored the raw `--version` output and printed it inside the program's own parentheses, which
  gave `Codex (codex-cli 0.160.0)` and, worse, `Claude Code (2.1.287 (Claude Code))`.

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
