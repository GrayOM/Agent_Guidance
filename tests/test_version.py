import re
import tomllib
from pathlib import Path

from agent_guidance import __version__


ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_uses_runtime_version_as_single_source() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["hatch"]["version"]["path"].endswith("__init__.py")


def test_the_version_matches_the_newest_changelog_section() -> None:
    """The invariant worth holding, instead of the literal that was here.

    This asserted `__version__ == "0.1.0"`, so every release broke it and the fix was to edit
    the number — a test that only ever confirms someone typed the same thing twice. What
    matters is that the version and the changelog agree: the release workflow takes the notes
    from the section matching the version, and a bump without a section produces an empty
    release, which `scripts/release_notes.py` already refuses.
    """
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^##\s+(\S+)", changelog, flags=re.M)
    assert headings, "CHANGELOG.md has no version headings"
    newest = headings[0]
    if newest.lower() == "unreleased":
        # A section still being written is fine; the one under it has to be the release.
        assert len(headings) > 1, "CHANGELOG.md has only an Unreleased section"
        newest = headings[1]
    assert __version__ == newest, (
        f"__version__ is {__version__} and the newest changelog section is {newest}"
    )
