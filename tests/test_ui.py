from rich.console import Console

from grayom_agent_guidance.cli.ui import LOGO, show_header


def test_the_mark_fits_the_header_column_and_avoids_the_pointer() -> None:
    """The mark, and the three things that went wrong with the art it replaced.

    A five-row eye had arrowheads on its outer corners, which read as a media control; redrawn
    as a tapered lid it read as a chip; and the eye itself, once it worked, read as nmap's.
    Rendered at the width a 96-column terminal occupies, every multi-row attempt came out as
    scattered brackets, so the drawing lives in docs/assets/grayom-mark.svg and this is a mark.

    The pointer is the sharp one: scripts/capture_screens.py takes a line starting with U+276F
    as a question waiting for an answer, so a header carrying one would have the capture typing
    into the startup banner.
    """
    assert ">_" in LOGO
    assert "\u276f" not in LOGO, "the capture script reads this character as a waiting prompt"
    assert "\u25c9" not in LOGO and "\u25c0" not in LOGO, "the eye and its arrowheads are gone"
    rows = [line for line in LOGO.splitlines() if line.strip()]
    assert len(rows) == 1, "a multi-row mark does not survive being rendered at terminal width"
    # show_header gives the mark 2 of 5 columns, so at the 78-column minimum it has about 31.
    assert max(len(line) for line in rows) <= 31


def test_header_prints_product_name() -> None:
    console = Console(record=True, color_system=None, width=100)
    show_header(console)

    output = console.export_text()
    assert "GrayOM" in output
    assert "AGENT GUIDANCE" in output
    assert "AI Agent Environment Manager" in output
    assert "WELCOME TO" in output


def test_header_stacks_safely_on_narrow_terminals() -> None:
    console = Console(record=True, color_system=None, width=60)
    show_header(console)

    output = console.export_text()
    assert "GrayOM" in output
    assert ">_" in output, "the mark has to survive the stacked layout too"
