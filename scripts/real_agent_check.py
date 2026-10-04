"""Run Agent Guidance against the Agents actually installed on this machine.

The audit's standing gap is that every end-to-end run happened on Linux against isolated
fixtures or this developer's container. This script closes it by doing the whole thing for
real — detect, install, health check, uninstall, verify nothing of Agent Guidance's is left — inside a
throwaway HOME, so it can run on a CI runner and on a user's own machine with one command.

The throwaway HOME is not empty. It is seeded with the Agent configuration a person actually
keeps — a comment explaining a choice, an option they set deliberately, an MCP server they
registered themselves — because the promise the README makes is about merging into that, and an
empty HOME cannot exercise it. The run then checks all of it survived the install and that
rollback restores the files byte for byte.

It needs no credentials: discovery runs offline against the Local Registry, and installation
clones the pinned Skill repositories over HTTPS. Everything it writes lives under a temporary
directory that is removed on the way out.

    python scripts/real_agent_check.py            # every detected Agent
    python scripts/real_agent_check.py --require codex claude_code
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Hand-written Agent configuration of the shape a person keeps: a comment that explains a
# choice, an option set deliberately, and an MCP server registered by hand with its own args
# and environment. The install has to merge into this and leave every part of it alone.
EXISTING_CODEX = """\
# My own settings. Do not lose these.
model = "o3"
approval_policy = "on-request"

[mcp_servers.my_own_server]
command = "python3"
args = ["-m", "my_internal_tools.mcp"]

[mcp_servers.my_own_server.env]
MY_ENDPOINT = "https://internal.example.test"
"""

EXISTING_CLAUDE = {
    "mcpServers": {
        "my_own_server": {"command": "python3", "args": ["-m", "my_internal_tools.mcp"]},
    },
    "someUnrelatedSetting": {"keepMe": True},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require", nargs="*", default=[],
        help="Agent names that must be detected; the run fails if one is missing",
    )
    arguments = parser.parse_args()

    # Resolved because Agent Guidance refuses to manage a path with a symlink in it, and macOS puts
    # the temporary directory under /var, which is a symlink to /private/var.
    workspace = Path(tempfile.mkdtemp(prefix="agent-guidance-real-agent-")).resolve()
    home = workspace / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text(EXISTING_CODEX, encoding="utf-8")
    (home / ".claude").mkdir()
    (home / ".claude.json").write_text(
        json.dumps(EXISTING_CLAUDE, indent=2), encoding="utf-8"
    )
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)  # Path.home() reads this one on Windows
    os.environ["AGENT_GUIDANCE_HOME"] = str(workspace / "agent-guidance")
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GH_TOKEN", None)
    try:
        return check(home, arguments.require)
    except ImportError as exc:
        # Adding src to sys.path makes the package importable without making its dependencies
        # available, so a fresh clone fails on the first one an adapter imports. A stack trace
        # out of the middle of an adapter reads as a broken program; it means nothing is
        # installed. See scripts/design_check.py, where the same trap was found first.
        print(
            f"\nAgent Guidance is not installed in this Python: {exc.name or exc} is missing."
            f"\nInstall it first:  python -m pip install -e \"{ROOT}\"",
            file=sys.stderr,
        )
        return 3
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def check(home: Path, required: list[str]) -> int:
    from agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
    from agent_guidance.adapters.detection import detect_agents
    from agent_guidance.cli.interview import build_answer
    from agent_guidance.config import load_config
    from agent_guidance.core.discovery import discover_components_sync
    from agent_guidance.core.multi_agent_installer import (
        MultiAgentInstallationTransaction, rollback_multi_agent,
    )
    from agent_guidance.core.multi_agent_plan import build_multi_agent_plan
    from agent_guidance.core.recommender import recommend
    from agent_guidance.core.uninstall import apply_uninstall, plan_uninstall
    from agent_guidance.models import AgentType, SetupMode, WorkDomain
    from agent_guidance.state import StateStore

    failures: list[str] = []

    def record(ok: bool, label: str, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print(f"platform: {sys.platform} | python {sys.version.split()[0]} | HOME={home}")

    print("\n[detect]")
    detected = detect_agents()
    present = []
    for installation in detected:
        found = installation.detected
        print(
            f"  {'found' if found else '  -  '} {installation.agent.value}"
            f"{' ' + str(installation.version) if installation.version else ''}"
        )
        if found:
            present.append(installation.agent)
    for name in required:
        record(any(item.value == name for item in present), f"{name} is detected")
    if not present:
        record(False, "at least one Agent is detected")
        return report(failures)

    adapters = {AgentType.CODEX: CodexAdapter(home), AgentType.CLAUDE_CODE: ClaudeCodeAdapter(home)}

    print("\n[install]")
    # PERFORMANCE, and these tasks, because the preservation checks below read the Agent
    # configuration files and only an MCP server causes those to be written at all. Under
    # MINIMAL with secure_code_review the recommendation is Skills only, which land in
    # ~/.agents/skills and leave config.toml untouched — so every "kept a comment" check
    # passed without the merge code running once. The guard below now makes that a failure
    # rather than a silent pass.
    answer = build_answer(
        agents=present,
        domains=[WorkDomain.PENETRATION_TESTING],
        tasks=["web_application_assessment", "injection_testing", "assessment_reporting"],
        mode=SetupMode.PERFORMANCE,
    )
    # Offline keeps the run deterministic: the Local Registry is the input, and installation
    # still clones the pinned repositories for real.
    discovery = discover_components_sync(answer, offline=True)
    plan = recommend(answer, discovery.candidates)
    multi = build_multi_agent_plan(
        plan, {item.agent: item for item in detected}, adapters,
        skill_limit=load_config().skills.max_per_component,
    )
    record(bool(multi.agents), "the Plan covers at least one Agent")
    result = MultiAgentInstallationTransaction(
        {agent: adapters[agent] for agent in multi.agents},
        Path(os.environ["AGENT_GUIDANCE_HOME"]) / "backups",
    ).execute(multi, probe_mcp=False)
    record(result.success, "the install transaction committed", str(result.error or ""))
    if not result.success:
        return report(failures)
    for outcome in result.manifest.outcomes:
        print(f"    {outcome.agent.value}: {outcome.name} — {outcome.summary()}")

    print("\n[preserved]")
    # The README's promise to anyone with an existing setup: "기존 설정은 덮어쓰지 않고 merge
    # 합니다. 주석, 직접 등록한 MCP 서버, 기존 옵션 모두 유지됩니다." Nothing checked it, because
    # every end-to-end run started from an empty HOME, where there is nothing to preserve.
    codex_after = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    claude_raw = (home / ".claude.json").read_text(encoding="utf-8")
    # Without this the whole section is vacuous: an install that writes to neither file keeps
    # every fragment by doing nothing, and a broken merge would read as a pass.
    record(
        codex_after != EXISTING_CODEX,
        "the install wrote to the Codex config, so merging was exercised",
    )
    record(
        json.loads(claude_raw) != EXISTING_CLAUDE,
        "the install wrote to the Claude Code config, so merging was exercised",
    )
    for fragment, label in (
        ("# My own settings. Do not lose these.", "a comment"),
        ('model = "o3"', "a hand-set option"),
        ("my_own_server", "a hand-registered MCP server"),
        ("my_internal_tools.mcp", "that server's args"),
        ("https://internal.example.test", "that server's env"),
    ):
        record(fragment in codex_after, f"codex kept {label}")
    claude_after = json.loads(claude_raw)
    record(
        "my_own_server" in (claude_after.get("mcpServers") or {}),
        "claude_code kept a hand-registered MCP server",
    )
    record(
        claude_after.get("someUnrelatedSetting") == {"keepMe": True},
        "claude_code kept an unrelated setting",
    )

    print("\n[health]")
    for agent, health in result.health.items():
        fatal = [check.name for check in health.checks if not check.passed and check.fatal]
        record(not fatal, f"{agent.value} health has no fatal failure", ", ".join(fatal))

    state = StateStore()
    state.record(multi, result.manifest)
    installed = sorted(StateStore().document.components)
    record(bool(installed), "state recorded what was installed", ", ".join(installed))

    print("\n[uninstall]")
    uninstall_plan = plan_uninstall(StateStore())
    record(not uninstall_plan.empty, "the uninstall plan is not empty")
    removal = apply_uninstall(uninstall_plan, adapters, StateStore())
    record(removal.successful, "the uninstall reported no error", "; ".join(removal.errors))
    for item in removal.removals:
        detail = ", ".join(
            part for part in (
                f"{len(item.removed_paths)} dirs" if item.removed_paths else "",
                f"mcp {','.join(item.removed_mcp)}" if item.removed_mcp else "",
            ) if part
        )
        print(f"    {item.component_id}: {detail or 'nothing'}")

    # The user-facing promise of `agent-guidance uninstall`: the config goes back. It is
    # checked to the byte, against a file that had content before the install, because
    # restoring an empty file proves nothing. This caught a blank line that the removal of an
    # MCP table left behind, which made a config that ended in one newline come back ending
    # in two.
    record(
        (home / ".codex" / "config.toml").read_text(encoding="utf-8") == EXISTING_CODEX,
        "uninstall restored the Codex config byte for byte",
    )
    record(
        json.loads((home / ".claude.json").read_text(encoding="utf-8")) == EXISTING_CLAUDE,
        "uninstall restored the Claude Code config exactly",
    )

    print("\n[rollback]")
    # Rollback is the other half of the same promise, and it has to be checked against a file
    # that had content before the install — restoring an empty file proves nothing. It runs
    # here, on a fresh install, because doing it earlier would undo the install the uninstall
    # section above needs.
    second = MultiAgentInstallationTransaction(
        {agent: adapters[agent] for agent in multi.agents},
        Path(os.environ["AGENT_GUIDANCE_HOME"]) / "backups",
    ).execute(multi, probe_mcp=False)
    if not second.success:
        record(False, "a second install for the rollback check committed", str(second.error or ""))
    else:
        outcomes = rollback_multi_agent(
            second.manifest, {agent: adapters[agent] for agent in multi.agents},
        )
        # Each Agent gets its own RollbackResult; the dict is always truthy, so the errors
        # inside it are what to read.
        errors = {agent.value: item.errors for agent, item in outcomes.items() if item.errors}
        record(not errors, "rollback reported no error", str(errors))
        record(
            (home / ".codex" / "config.toml").read_text(encoding="utf-8") == EXISTING_CODEX,
            "rollback restored the Codex config byte for byte",
        )
        record(
            json.loads((home / ".claude.json").read_text(encoding="utf-8")) == EXISTING_CLAUDE,
            "rollback restored the Claude Code config exactly",
        )

    print("\n[verify]")
    for agent in present:
        adapter = adapters[agent]
        leftover = [
            name for name in adapter.list_existing_skills()
            if any(name.startswith(f"{component}--") for component in installed)
        ]
        record(not leftover, f"{agent.value} has no Agent Guidance Skill left", ", ".join(leftover))
    config = home / ".claude.json"
    if config.exists():
        servers = json.loads(config.read_text(encoding="utf-8")).get("mcpServers") or {}
        record(
            not [name for name in servers if name in installed],
            "Claude Code has no Agent Guidance MCP registration left",
        )
    return report(failures)


def report(failures: list[str]) -> int:
    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("All real-Agent checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
