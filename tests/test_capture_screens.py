"""The screenshot script's option indices, checked against the real option lists.

scripts/capture_screens.py drives the interview by counting arrow keys, so an option inserted
into TASKS or WorkDomain silently moves what the screenshots photograph. The capture itself is
not run here: it needs a real Codex and Claude Code, takes minutes, and its output legitimately
changes whenever those Agents are upgraded, so it is a poor gate. The indices are the part that
can go wrong quietly, so they are the part held in place.
"""

import importlib.util
from pathlib import Path

import pytest

from grayom_agent_guidance.cli.interview import TASKS
from grayom_agent_guidance.labels import domain_label, task_label
from grayom_agent_guidance.models import WorkDomain


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"


@pytest.fixture(scope="module")
def capture():
    """Import the script by path: scripts/ is not a package and is not installed."""
    spec = importlib.util.spec_from_file_location(
        "capture_screens", ROOT / "scripts" / "capture_screens.py"
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:  # pyte is a documentation dependency, not a runtime one
        pytest.skip(f"capture_screens is not importable here: {exc}")
    return module


def test_the_domain_indices_still_name_the_domains_the_readme_describes(capture):
    domains = list(WorkDomain)
    assert domains[capture.SECURITY_DOMAIN] is WorkDomain.PENETRATION_TESTING
    assert domains[capture.OSINT_DOMAIN] is WorkDomain.OSINT
    # The capture walks from one to the other with a single "down".
    assert capture.OSINT_DOMAIN == capture.SECURITY_DOMAIN + 1


def test_the_task_indices_still_name_the_tasks_the_readme_describes(capture):
    tasks = TASKS[WorkDomain.PENETRATION_TESTING]
    chosen = [tasks[index] for index in capture.ASSESSMENT_TASKS]
    assert chosen == ["web_application_assessment", "authentication_testing", "injection_testing"]


def test_every_screen_has_an_image_and_every_image_is_committed(capture):
    for screen in capture.SCREENS:
        images = screen.get("images") or [screen]
        for image in images:
            assert (ASSETS / f"{image['name']}.svg").exists(), (
                f"{image['name']}.svg is missing; run python scripts/capture_screens.py"
            )


def test_no_screenshot_is_left_in_the_assets_directory_unused(capture):
    """A screenshot nobody regenerates is one that quietly stops matching the program."""
    produced = {
        f"{image['name']}.svg"
        for screen in capture.SCREENS
        for image in (screen.get("images") or [screen])
    }
    # The mark is drawn by hand on purpose; everything else is captured.
    on_disk = {path.name for path in ASSETS.glob("*.svg")} - {"grayom-mark.svg"}
    assert on_disk == produced


def test_the_readme_shows_every_captured_screenshot(capture):
    readme = (ROOT / "README.md").read_text()
    for screen in capture.SCREENS:
        for image in screen.get("images") or [screen]:
            assert f"docs/assets/{image['name']}.svg" in readme, (
                f"{image['name']}.svg is captured but the README never shows it"
            )


def test_the_labels_the_screenshots_show_are_the_ones_the_readme_names(capture):
    """Guards the README's walkthrough text, which quotes these labels."""
    assert domain_label(WorkDomain.PENETRATION_TESTING) == "Penetration testing and assessment"
    assert task_label("web_application_assessment") == "Web application assessment"
