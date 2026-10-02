"""Run Agent Guidance against the Agents actually installed on this machine.

The audit's standing gap is that every end-to-end run happened on Linux against isolated
fixtures or this developer's container. This script closes it by doing the whole thing for
real — detect, install, health check, uninstall, verify nothing of Agent Guidance's is left — inside a
throwaway HOME, so it can run on a CI runner and on a user's own machine with one command.

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
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)  # Path.home() reads this one on Windows
    os.environ["AGENT_GUIDANCE_HOME"] = str(workspace / "agent-guidance")
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GH_TOKEN", None)
    try:
        return check(home, arguments.require)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def check(home: Path, required: list[str]) -> int:
    from agent_guidance.adapters import ClaudeCodeAdapter, CodexAdapter
    from agent_guidance.adapters.detection import detect_agents
    from agent_guidance.cli.interview import build_answer
    from agent_guidance.config import load_config
    from agent_guidance.core.discovery import discover_components_sync
    from agent_guidance.core.multi_agent_installer import (
        MultiAgentInstallationTransaction,
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
    answer = build_answer(
        agents=present,
        domains=[WorkDomain.PENETRATION_TESTING],
        tasks=["web_application_assessment", "secure_code_review", "assessment_reporting"],
        mode=SetupMode.MINIMAL,
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
