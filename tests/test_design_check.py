"""The design check's verdict, which is the one thing a reader acts on.

This script exists to answer one question before the project is published anywhere: does it do
what it was designed to do, on the machine running it. Its exit code is the answer, so the
three outcomes have to stay distinct. A blocked network must not read as a defect, or the next
person to see this output learns to ignore it.
"""

import builtins
import importlib.util
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def report():
    from agent_guidance.core.self_check import Report

    return Report()


def test_everything_passing_exits_zero(report, capsys) -> None:
    report.check(True, "a claim", "what it measured")
    assert report.verdict() == 0
    assert "Every claim passed" in capsys.readouterr().out


def test_a_failed_claim_exits_one(report, capsys) -> None:
    report.check(False, "a broken claim", "what it measured")
    assert report.verdict() == 1
    assert "a broken claim" in capsys.readouterr().out


def test_an_unreachable_claim_exits_two_and_not_one(report, capsys) -> None:
    """The distinction this file is for: unproven is not failed.

    Discovery degrades rather than raising when GitHub cannot be reached, so without this
    separation a user behind a firewall would see a failure and conclude the program is broken.
    """
    report.check(True, "a claim that passed", "measured")
    report.cannot_tell("a claim nothing could reach", "the network refused")
    assert report.verdict() == 2
    output = capsys.readouterr().out
    assert "Still unproven here" in output
    assert "a claim nothing could reach" in output


def test_a_failure_outranks_an_unproven_claim(report) -> None:
    """A real failure must not be hidden behind an unreachable one."""
    report.check(False, "a broken claim", "measured")
    report.cannot_tell("a claim nothing could reach", "the network refused")
    assert report.verdict() == 1


def test_the_check_names_the_claims_the_readme_promises() -> None:
    source = (ROOT / "src" / "agent_guidance" / "core" / "self_check.py").read_text(
        encoding="utf-8"
    )
    for number in range(1, 7):
        assert f"[{number}]" in source, f"claim {number} is not printed"
    assert "self-check" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_script_answers_a_missing_install_instead_of_raising(capsys) -> None:
    """The defect this file now also covers.

    scripts/design_check.py puts src on sys.path, which makes the package importable without
    making its dependencies available. The first person to run it on a fresh clone got
    `ModuleNotFoundError: tomlkit` out of the middle of an adapter: a stack trace that reads
    as a broken program and means nothing was installed.
    """
    spec = importlib.util.spec_from_file_location(
        "design_check", ROOT / "scripts" / "design_check.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("agent_guidance"):
            raise ModuleNotFoundError("No module named 'tomlkit'", name="tomlkit")
        return real_import(name, *args, **kwargs)

    with mock.patch.object(builtins, "__import__", refuse):
        assert script.main() == 3

    message = capsys.readouterr().err
    assert "tomlkit" in message
    assert "pip install" in message and "agent-guidance self-check" in message
    assert "Traceback" not in message


def test_the_command_is_how_the_check_is_meant_to_be_run() -> None:
    """A command can only run where the program is installed, so its dependencies are there."""
    from agent_guidance.cli.main import app

    names = {command.name or command.callback.__name__ for command in app.registered_commands}
    assert "self-check" in names


def component(**install):
    """A candidate carrying only what the pinning claim reads."""
    from agent_guidance.models import Component, ComponentType, InstallMethod

    return Component(
        id=install.pop("id", "candidate"), name="Candidate", type=ComponentType.SKILL,
        github_url="https://github.com/owner/repo",
        install_method=InstallMethod(**install),
    )


def test_a_pin_counts_whichever_route_its_kind_uses() -> None:
    """A Skill pins to a commit and an npm MCP server pins to a registry version.

    Both answer the same question, so the claim has to read both. Reading only `ref` would
    report a correctly pinned npm server as unpinned.
    """
    from agent_guidance.models import InstallKind
    from agent_guidance.core.self_check import _pin

    assert _pin(component(kind=InstallKind.GIT_SKILLS,
                          repository="https://github.com/owner/repo", ref="a" * 40))
    assert _pin(component(kind=InstallKind.MCP_STDIO, command="npx",
                          package="thing", package_version="1.2.3")) == "thing@1.2.3"
    # A branch name is not a pin: it resolves to something different later.
    assert not _pin(component(kind=InstallKind.GIT_SKILLS,
                              repository="https://github.com/owner/repo", ref="main"))
    assert not _pin(component(kind=InstallKind.MCP_STDIO, command="npx"))


def test_the_pinning_claim_counts_how_many_of_how_many(report, capsys) -> None:
    """The defect in the claim itself.

    It asserted `bool(pinned)`, so a run with three of four candidates pinned printed PASS and
    listed the three. The gap was invisible, and one pin in a hundred would have read the same.
    """
    from agent_guidance.core.self_check import _pin

    pinnable = [
        component(id="pinned-skill", kind="git_skills",
                  repository="https://github.com/owner/repo", ref="b" * 40),
        component(id="unpinned-mcp", kind="mcp_stdio", command="npx", from_readme=True),
    ]
    pinned = [item for item in pinnable if _pin(item)]
    unpinned = [item for item in pinnable if not _pin(item)]

    report.check(
        bool(pinnable) and not unpinned,
        "every discovered candidate on offer is pinned to an exact version",
        f"{len(pinned)} of {len(pinnable)} pinned; not pinned: unpinned-mcp",
    )
    assert report.verdict() == 1
    output = capsys.readouterr().out
    assert "1 of 2 pinned" in output
    assert "unpinned-mcp" in output


def fake_discovery(*, read_failures: int, candidates=(), discovered: int = 0):
    """A DiscoveryResult shaped like the run being reproduced."""
    from agent_guidance.core.discovery import DiscoveryResult
    from agent_guidance.sources.base import SourceResult

    return DiscoveryResult(
        candidates=list(candidates),
        sources=[SourceResult(
            source="github", checked=True, discovered=discovered,
            validated=len(candidates), read_failures=read_failures,
        )],
        warnings=["GitHub rate limit reached (remaining=0)"] if read_failures else [],
    )


def test_a_rate_limited_run_is_unproven_not_failed(report, monkeypatch, capsys) -> None:
    """The regression this covers, which shipped twice in different shapes.

    An anonymous run gets 60 GitHub requests an hour. A second run inside that hour reaches
    the search endpoint, is told about repositories, and is then refused every one of them.
    The `checked` flag is True, so the earlier guard passes, and the claims that read the
    candidate list then found it empty and reported two FAILs and exit 1 — a user being told
    their program is broken because they ran the check twice.
    """
    from agent_guidance.core import self_check as module

    monkeypatch.setattr(
        module, "discover_components_sync",
        lambda *a, **k: fake_discovery(read_failures=5, discovered=5),
    )
    module.live_github_discovery(_answer(), fake_discovery(read_failures=0), report)

    assert report.verdict() == 2, "a refused read must not read as a defect"
    output = capsys.readouterr().out
    assert "refused 5 of them" in output
    assert "GITHUB_TOKEN" in output
    assert "FAIL" not in output


def test_discovering_nothing_pinnable_is_unproven_not_failed(report, monkeypatch, capsys) -> None:
    """An empty set satisfies "every candidate is pinned" vacuously, which proves nothing."""
    from agent_guidance.core import self_check as module
    from agent_guidance.models import Component, ComponentType, InstallKind, InstallMethod

    http_only = Component(
        id="http-mcp", name="HTTP MCP", type=ComponentType.MCP,
        github_url="https://github.com/someone/http-mcp",
        install_method=InstallMethod(kind=InstallKind.MCP_HTTP, url="https://x.test/mcp/"),
        recommendable=True,
    )
    monkeypatch.setattr(
        module, "discover_components_sync",
        lambda *a, **k: fake_discovery(read_failures=0, candidates=[http_only], discovered=1),
    )
    module.live_github_discovery(_answer(), fake_discovery(read_failures=0), report)

    assert report.verdict() == 2
    output = capsys.readouterr().out
    assert "nothing with a version to pin" in output
    assert "FAIL" not in output


def _answer():
    from agent_guidance.cli.interview import build_answer
    from agent_guidance.models import AgentType, SetupMode, WorkDomain

    return build_answer(
        agents=[AgentType.CODEX], domains=[WorkDomain.PENETRATION_TESTING],
        tasks=["web_application_assessment"], mode=SetupMode.MINIMAL,
    )
