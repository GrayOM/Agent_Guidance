"""The design check's verdict, which is the one thing a reader acts on.

This script exists to answer one question before the project is published anywhere: does it do
what it was designed to do, on the machine running it. Its exit code is the answer, so the
three outcomes have to stay distinct. A blocked network must not read as a defect, or the next
person to see this output learns to ignore it.
"""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def report():
    spec = importlib.util.spec_from_file_location(
        "design_check", ROOT / "scripts" / "design_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Report()


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


def test_the_script_names_the_claims_the_readme_promises() -> None:
    """The script and the README have to describe the same six claims."""
    source = (ROOT / "scripts" / "design_check.py").read_text(encoding="utf-8")
    for number in range(1, 7):
        assert f'[{number}]' in source, f"claim {number} is not printed"
    assert "design_check.py" in (ROOT / "README.md").read_text(encoding="utf-8")
