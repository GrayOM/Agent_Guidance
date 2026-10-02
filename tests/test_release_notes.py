"""The release body is taken from CHANGELOG.md, so the extraction has to be exact.

The release workflow pipes scripts/release_notes.py into `gh release create`. If it returned
the wrong section, or silently returned nothing, the release would carry the wrong notes and
the tag would already be pushed by then.
"""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def notes():
    spec = importlib.util.spec_from_file_location(
        "release_notes", ROOT / "scripts" / "release_notes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLE = """# Changelog

## 0.2.0 — 2026-11-01

Second.

### Added

- a thing

## 0.1.0 — 2026-10-02

First.

### Added

- another thing

## 0.1.0rc1 — 2026-09-30

Candidate.
"""


def test_a_version_returns_its_own_section(notes) -> None:
    body = notes.extract("0.1.0", SAMPLE)
    assert body.startswith("First.")
    assert "another thing" in body
    assert "Second." not in body
    assert "Candidate." not in body


def test_a_release_is_not_confused_with_its_candidate(notes) -> None:
    """0.1.0 sits directly above 0.1.0rc1, so a prefix match would run the two together."""
    assert "Candidate." not in notes.extract("0.1.0", SAMPLE)
    assert notes.extract("0.1.0rc1", SAMPLE).strip() == "Candidate."


def test_the_newest_section_stops_at_the_next_heading(notes) -> None:
    assert notes.extract("0.2.0", SAMPLE).strip().endswith("- a thing")


def test_a_missing_version_raises_rather_than_returning_nothing(notes) -> None:
    """An empty release body would be published without complaint; this stops the workflow."""
    with pytest.raises(LookupError):
        notes.extract("9.9.9", SAMPLE)


def test_the_version_this_repository_ships_has_notes(notes) -> None:
    from agent_guidance import __version__

    body = notes.extract(__version__, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert len(body) > 200, "the release body is too short to be the real section"
