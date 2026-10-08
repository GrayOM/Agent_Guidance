<p align="center">
  <img src="docs/assets/agent-guidance-mark.svg" width="140" alt="Agent Guidance">
</p>

<h1 align="center">Agent Guidance</h1>

<p align="center"><sub>by GrayOM</sub></p>

<p align="center"><b>English</b> · <a href="README.ko.md">한국어</a></p>

<p align="center">
  <strong>A CLI that decides which skills, MCP servers and plugins to install for Codex and Claude Code</strong>
</p>

<p align="center">
  You pick the work you do. You don't need to know, or choose between, skill, MCP or plugin names.
</p>

---

## One command

```bash
agent-guidance
```

Everything else is arrow keys and Enter.

<img src="docs/assets/menu.svg" alt="agent-guidance start screen - detects installed agents and shows the menu">

It first detects which agents are installed and shows their versions, then asks what you want to
do. Every menu entry says **what will happen if you pick it**, so there is no guessing on the
first run.

> Every screenshot in this document was captured from the real program
> (`python scripts/capture_screens.py`). None of them are mock-ups.

---

## Install

The same command on Windows, macOS and Linux.

```bash
pipx install "git+https://github.com/GrayOM/Agent_Guidance.git@main"
```

<details>
<summary>Requirements, and what to do without pipx</summary>

You need:

- Python 3.11 or later
- Git
- **At least one of** Codex or Claude Code already installed
  (Agent Guidance does not install the agents themselves)

Without pipx, see the [pipx installation guide](https://pipx.pypa.io/stable/installation/), or
install into a virtual environment:

```bash
git clone https://github.com/GrayOM/Agent_Guidance.git
cd Agent_Guidance
python -m venv .venv
```

Activate it (`.venv\Scripts\Activate.ps1` in Windows PowerShell, `source .venv/bin/activate` on
macOS and Linux), then:

```bash
python -m pip install .
agent-guidance
```

If `agent-guidance` is not found, run `pipx ensurepath` and open a new terminal. Failing that,
`python -m agent_guidance` does exactly the same thing.

</details>

---

## How it works

### 1. Pick your fields (multi-select)

<img src="docs/assets/interview-domains.svg" alt="Field selection screen - penetration testing and OSINT selected">

Space toggles, Enter moves on. Installed agents are **pre-selected**, so Enter alone is fine.

There are 11 fields:

- General development
- Web development
- Mobile development
- AI Agent development
- Security tool development
- Vulnerability research
- **Penetration testing and assessment**
- OSINT
- DevOps
- Data analysis
- Research and writing

### 2. Pick the tasks within each field (multi-select)

Each field you chose gets one more question. This is where the accuracy of the recommendation
comes from.

<img src="docs/assets/interview-tasks.svg" alt="Penetration testing task selection - web application assessment, authentication testing and injection testing selected">

Penetration testing and assessment asks about 13 tasks, as above: Web application assessment,
Authentication testing, Authorisation testing, Injection testing, API security testing, Mobile
application assessment, Secure code review, Infrastructure testing, Configuration assessment,
Cloud configuration assessment, Finding reproduction and PoC, Assessment reporting and Retest
verification. Across all 11 fields there are 78 tasks.

Finally, choose a setup mode:

- **Minimal** — only what is strictly needed
- **Performance** — a broader, specialist setup

> It never asks things like "Do you need the GitHub MCP server?". You describe the work; Agent
> Guidance infers the capabilities that work needs.

### 3. Everything is shown before anything is installed

<img src="docs/assets/plan.svg" alt="Recommendation screen - selected components and the reasons for each">

- The skills, MCP servers and plugins to be installed, and **why each was chosen**
- Which of your answers each capability was inferred from (`Inferred from:`)
- How many candidates were considered and **excluded**, and why
- Capabilities no candidate could cover (`No verified candidate covers:`) — a gap is reported as a
  gap, not papered over

Then, per agent, the actual changes and the security review:

<img src="docs/assets/plan-approval.svg" alt="Change list and security review screen">

- ADD/SKIP and compatibility for each agent
- File, network, shell and credential access risk (`LOW` / `WARNING`)
- Components whose functionality overlaps (`Conflicts`)
- How many will be installed, and that existing configuration is backed up and merged

`WARNING` does not block the install; it is **information you should have before approving**.
Until you press Enter here, not one character of any agent configuration file changes.

---

## Safety

- Nothing is written before final approval.
- Existing configuration is **merged**, not overwritten. Comments, MCP servers you registered
  yourself and existing options are all preserved.
- Every target agent is **fully backed up** before installing.
- Components you installed yourself are left alone.
- If anything fails midway, only what this run created is removed and the original state is
  restored.
- Tokens, passwords, OAuth values and SSH keys are never written to logs or state files.
- **Everything installed is pinned.** Skills and plugins are pinned to a commit (`head_sha`); MCP
  servers launched through npm are pinned to a registry version. A newer upload never runs
  silently later.
- **An MCP server's launch command comes from that repository's README.** A README is the owner's
  prose, not a verified manifest, so a server is only recommended after the registry confirms the
  npm package **exists** and **declares that repository as its own**. If it cannot be confirmed it
  is dropped, and the approval screen warns that the command was read from a README.

Details are in [SECURITY.md](SECURITY.md) and the [threat model](docs/threat-model.md).

---

## When something goes wrong

Day to day, `agent-guidance` is all you need. The commands below are for when something looks off.

```bash
agent-guidance doctor      # check that agents and installed components are still healthy
agent-guidance rollback    # undo the last change
agent-guidance uninstall   # remove what Agent Guidance installed (files you created stay)
agent-guidance debug-info  # diagnostics for a bug report (no tokens or passwords)
```

<img src="docs/assets/doctor.svg" alt="agent-guidance doctor output">

All of these are also in the menu. There is nothing to memorise.

<details>
<summary>Full <code>agent-guidance --help</code></summary>

<img src="docs/assets/help.svg" alt="agent-guidance --help output">

</details>

### Updating and removing

```bash
pipx upgrade agent-guidance    # update Agent Guidance itself
pipx uninstall agent-guidance  # remove Agent Guidance
```

Removing Agent Guidance does not revert configuration it already applied. To revert that too, run
`agent-guidance rollback` or `agent-guidance uninstall` first.

---

## Support

| Agent | Detect | Skill | MCP | Plugin | Doctor / rollback |
|---|:---:|:---:|:---:|:---:|:---:|
| Codex | O | O | O | — | O |
| Claude Code | O | O | O | O | O |

Codex has no plugin format to install automatically.

Claude Code plugins are delegated to the `claude plugin` command and wrapped in an Agent Guidance
transaction. If `claude` cannot be run, plugins are left out of the recommendation. Only plugins a
marketplace manifest declares are installed; both steps, `marketplace add` and `install`, record
only what this run added and are undone in reverse order. **A plugin that requires accepting a
command declared by its marketplace is never auto-approved** — you are shown the command to run
yourself.

---

## Good to know

- State, backups, cache and logs live in `~/.agent-guidance/`. Neither your full answer profile nor
  any credential value is stored.
- Candidates come from the built-in registry and from GitHub. `GITHUB_TOKEN` widens the candidate
  pool; it works without one.
- To work offline: `agent-guidance setup --offline` uses only the built-in registry and verified
  cache. The plan screenshot above was captured in this mode, so a live run shows more candidates.
- **To check it behaves as designed** — installs nothing and writes nothing outside a temporary
  directory:

  ```bash
  agent-guidance self-check
  ```

  It prints six checks, each with what it measured. Exit code `0` means all passed, `1` means a
  failure, and `2` means everything checkable passed but GitHub discovery could not be checked.
  **`2` is not a defect in the program.**

  Without `GITHUB_TOKEN`, GitHub allows 60 requests an hour, so a second run within the hour cannot
  read repositories and returns `2`. Set `GITHUB_TOKEN` or wait an hour to see `0`.

  From an uninstalled clone, `python scripts/design_check.py` does the same, but needs the
  dependencies installed; if they are missing it prints the install command and exits.
- **If you used the earlier `grayom` command**: the author name (GrayOM) and project name (Agent
  Guidance) were untangled, so the command moved from `grayom` to `agent-guidance` and the state
  folder from `~/.grayom/` to `~/.agent-guidance/`. Old records are left in place; move
  `~/.grayom/` to `~/.agent-guidance/` to carry on with them. The program tells you this too.
- `agent-guidance uninstall` **does not delete a skill you edited after installing it** — a program
  should not delete files you rewrote. It tells you which directories were left, with their paths,
  so you can remove them yourself if you no longer need them.

---

## Developer documentation

- [Architecture](architecture.md)
- [Security policy](SECURITY.md)
- [Threat model](docs/threat-model.md)
- [Release audit](docs/release-audit.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

The current version is `0.2.0`.

## License

MIT
