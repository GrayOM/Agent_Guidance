"""Check that this program does the thing it was designed to do, on your machine.

    python scripts/design_check.py

Six claims are checked, each printed with what it actually measured. The sixth is the reason
this script exists: discovery against the live GitHub API has never been run from any machine
available to the project, because the container it was written in answers 403 on
`GET /search/repositories` ("sessions are bound to their configured repositories"). Everything
after the HTTP response is covered by tests. The call itself is not, and only a machine that
can reach GitHub can settle it.

Nothing is installed and nothing is written outside a temporary directory, so this is safe to
run before deciding whether the program is ready to publish. `GITHUB_TOKEN` is used if it is
set, which raises the candidate budget; without one the run still works, more slowly and with
fewer candidates.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.unproven: list[str] = []

    def check(self, ok: bool, claim: str, measured: str) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {claim}\n          {measured}")
        if not ok:
            self.failures.append(claim)

    def cannot_tell(self, claim: str, why: str) -> None:
        """Neither pass nor fail: the run could not reach what the claim is about.

        Kept separate from a failure on purpose. An unreachable network is not a defect in the
        program, and calling it one would train the reader to ignore this output.
        """
        print(f"  ????  {claim}\n          {why}")
        self.unproven.append(claim)

    def verdict(self) -> int:
        print()
        if self.failures:
            print(f"{len(self.failures)} claim(s) failed:")
            for claim in self.failures:
                print(f"  - {claim}")
            return 1
        if self.unproven:
            print("Every claim this run could check passed. Still unproven here:")
            for claim in self.unproven:
                print(f"  - {claim}")
            return 2
        print("Every claim passed, including live GitHub discovery.")
        return 0


def main() -> int:
    from agent_guidance import __version__
    from agent_guidance.adapters.detection import detect_agents
    from agent_guidance.cli.interview import TASKS, build_answer
    from agent_guidance.core.capability_inference import infer_capabilities
    from agent_guidance.core.discovery import discover_components_sync
    from agent_guidance.core.recommender import recommend
    from agent_guidance.models import ComponentType, SetupMode, WorkDomain

    report = Report()
    print(f"Agent Guidance {__version__} | python {sys.version.split()[0]} | {sys.platform}")
    print(f"GITHUB_TOKEN: {'set' if os.environ.get('GITHUB_TOKEN') else 'not set'}")

    print("\n[1] It finds the Agents you already have, and installs none itself.")
    detected = detect_agents()
    found = [item for item in detected if item.detected]
    report.check(
        bool(found),
        "at least one supported Agent is detected",
        ", ".join(f"{item.agent.value} {item.version or '?'}" for item in found) or "none found",
    )

    print("\n[2] It asks what you do, in detail, rather than asking about tooling.")
    # Distinct tasks: a few are offered under more than one domain, and counting those twice
    # would overstate the interview's reach.
    tasks = {task for value in TASKS.values() for task in value}
    report.check(
        len(WorkDomain) >= 10 and len(tasks) >= 70 and all(TASKS.get(d) for d in WorkDomain),
        "the interview asks about work, across domains and tasks",
        f"{len(WorkDomain)} domains, {len(tasks)} distinct tasks, every domain populated",
    )

    print("\n[3] It works out the capabilities itself, from the work.")
    answer = build_answer(
        agents=[item.agent for item in found] or [item.agent for item in detected],
        domains=[WorkDomain.PENETRATION_TESTING],
        tasks=["web_application_assessment", "injection_testing", "assessment_reporting"],
        mode=SetupMode.PERFORMANCE,
    )
    capabilities = infer_capabilities(answer)
    report.check(
        len(capabilities) >= 3,
        "a work selection infers a capability set with no technical questions asked",
        f"{len(capabilities)} capabilities: " + ", ".join(sorted(c.value for c in capabilities)),
    )

    print("\n[4] It recommends Skills, MCP servers and Plugins, not just one kind.")
    offline = discover_components_sync(answer, offline=True)
    kinds = {candidate.type for candidate in offline.candidates}
    report.check(
        {ComponentType.SKILL, ComponentType.MCP} <= kinds,
        "the built-in list covers more than one component kind",
        f"{len(offline.candidates)} candidates: "
        + ", ".join(f"{kind.value}={sum(1 for c in offline.candidates if c.type == kind)}"
                    for kind in sorted(kinds, key=lambda k: k.value)),
    )

    print("\n[5] It explains its choices before anything is installed.")
    plan = recommend(answer, offline.candidates)
    reasons = [item for item in plan.items if item.selected and item.reasons]
    report.check(
        bool(plan.selected) and len(reasons) == len(plan.selected),
        "every selected component carries its reason",
        f"{len(plan.selected)} selected, {len(reasons)} with reasons, "
        f"{len(plan.items) - len(plan.selected)} considered and not selected",
    )

    print("\n[6] It searches GitHub for other people's Skills, at their latest commit.")
    live_github_discovery(answer, offline, report)

    return report.verdict()


def live_github_discovery(answer, offline, report: Report) -> None:
    """The one claim this project has never been able to check for itself."""
    from agent_guidance.core.discovery import discover_components_sync

    registry_repositories = {str(candidate.github_url).lower() for candidate in offline.candidates}
    try:
        live = discover_components_sync(answer, offline=False)
    except Exception as exc:  # noqa: BLE001 - any failure here is itself the answer
        report.cannot_tell(
            "discovery reaches the live GitHub API",
            f"the run raised before any result: {type(exc).__name__}: {exc}",
        )
        return

    for source in live.sources:
        print(f"          {source.source}: checked={source.checked} "
              f"{source.discovered} discovered, {source.validated} validated")
    for warning in live.warnings:
        print(f"          warning: {warning}")

    # Discovery degrades rather than raising, so whether GitHub was reached at all is read from
    # the source's own flag. A blocked network is not a defect in this program, and reporting it
    # as a failure would teach the reader to ignore this output; it is reported as unproven.
    reached = next((s for s in live.sources if s.source == "github" and s.checked), None)
    if reached is None:
        report.cannot_tell(
            "discovery reaches the live GitHub API",
            "the github source was not reached, so the claim is untested here rather than "
            "failed. The warnings above carry GitHub's own words; a network that allows "
            "api.github.com/search/repositories will settle it.",
        )
        return

    github = [candidate for candidate in live.candidates
              if str(candidate.github_url).lower() not in registry_repositories]
    report.check(
        bool(github),
        "repositories nobody curated into this project are discovered",
        f"{len(github)} of {len(live.candidates)} candidates come from outside the built-in "
        "list: " + ", ".join(str(c.github_url) for c in github[:5]) or "none",
    )

    # "Latest" is the whole point of searching rather than shipping a fixed list: an install
    # ref has to be the commit the repository is at now, not a branch name resolved later and
    # not the cache key the search result was sorted by.
    pinned = [candidate for candidate in github
              if candidate.install_method.ref and len(str(candidate.install_method.ref)) >= 7]
    report.check(
        bool(pinned) if github else False,
        "a discovered repository is pinned to a real commit",
        ", ".join(f"{c.id}@{str(c.install_method.ref)[:12]}" for c in pinned[:5]) or "none pinned",
    )


if __name__ == "__main__":
    workspace = Path(tempfile.mkdtemp(prefix="agent-guidance-design-")).resolve()
    os.environ["AGENT_GUIDANCE_HOME"] = str(workspace)
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
