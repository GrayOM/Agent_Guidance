from pathlib import Path

from rich.console import Console

from agent_guidance.cli.ui import LOGO, show_header


def test_the_mark_fits_the_header_column_and_avoids_the_pointer() -> None:
    """The mark, and what went wrong with the art it replaced.

    A five-row eye had arrowheads on its outer corners, which read as a media control; redrawn
    as a tapered lid it read as a chip. At the width a 96-column terminal occupies, every
    multi-row attempt came out as scattered brackets, so the drawing lives in
    docs/assets/agent-guidance-mark.svg and this is a mark that echoes it.

    The pointer is the sharp one: scripts/capture_screens.py takes a line starting with U+276F
    as a question waiting for an answer, so a header carrying one would have the capture typing
    into the startup banner.
    """
    assert "\u25ce" in LOGO, "the mark echoes the SVG's reticle"
    assert "\u276f" not in LOGO, "the capture script reads this character as a waiting prompt"
    assert "\u25c0" not in LOGO and "\u25b6" not in LOGO, "the arrowheads read as a media control"
    rows = [line for line in LOGO.splitlines() if line.strip()]
    assert len(rows) == 1, "a multi-row mark does not survive being rendered at terminal width"
    # show_header gives the mark 2 of 5 columns, so at the 78-column minimum it has about 31.
    assert max(len(line) for line in rows) <= 31


def test_header_names_the_project_and_credits_its_author() -> None:
    """GrayOM is the person who wrote this; the project is Agent Guidance.

    The header used to put GrayOM where a product name goes, with AGENT GUIDANCE under it, so
    it read as though the program were called GrayOM Agent Guidance.
    """
    console = Console(record=True, color_system=None, width=100)
    show_header(console)

    output = console.export_text()
    assert "Agent Guidance" in output
    assert "AI Agent Environment Manager" in output
    assert "WELCOME TO" in output
    # The author is credited, and only as the author.
    assert "by GrayOM" in output
    assert output.count("GrayOM") == 1, "the author's name belongs on one line, as a credit"
    for line in output.splitlines():
        stripped = line.strip("│ ").strip()
        if stripped.startswith("GrayOM"):
            raise AssertionError(f"the author's name is standing in for the project: {line!r}")


def test_header_stacks_safely_on_narrow_terminals() -> None:
    console = Console(record=True, color_system=None, width=60)
    show_header(console)

    output = console.export_text()
    assert "Agent Guidance" in output
    assert "\u25ce" in output, "the mark has to survive the stacked layout too"


def test_the_old_state_directory_is_pointed_at_rather_than_moved(tmp_path, monkeypatch) -> None:
    """State lived in ~/.grayom when the author's name stood in for the project's.

    It is not moved on the user's behalf: that directory records what was installed into their
    Agents. Saying where it went is the point, because otherwise the first run after an upgrade
    looks like every installed component has vanished.
    """
    monkeypatch.delenv("AGENT_GUIDANCE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".grayom").mkdir()

    console = Console(record=True, color_system=None, width=100)
    show_header(console)

    output = console.export_text()
    assert ".grayom" in output and "~/.agent-guidance" in output
    assert (tmp_path / ".grayom").is_dir(), "the old directory is named, never relocated"


def test_no_notice_once_the_new_state_directory_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENT_GUIDANCE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".grayom").mkdir()
    (tmp_path / ".agent-guidance").mkdir()

    console = Console(record=True, color_system=None, width=100)
    show_header(console)
    assert ".grayom" not in console.export_text()
