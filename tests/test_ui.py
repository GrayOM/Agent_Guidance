from rich.console import Console

from grayom_agent_guidance.cli.ui import LOGO, show_header


def test_logo_is_an_eye_mark_that_fits_the_header_column() -> None:
    """The mark, and the two things that went wrong with the art it replaced.

    The first version was a five-row outline with arrowheads on its outer corners, asserted
    here by the character. Rendered at the width a 96-column terminal occupies, every
    multi-row attempt read as scattered brackets rather than an eye, and the arrowheads read
    as a media control. The eye proper is docs/assets/grayom-eye.svg; this is a mark, so what
    matters is that it is present, short, and narrow enough for the column it is drawn in.
    """
    assert "◉" in LOGO
    assert "◀" not in LOGO and "▶" not in LOGO
    rows = [line for line in LOGO.splitlines() if line.strip()]
    assert len(rows) == 1, "a multi-row mark does not survive being rendered at terminal width"
    # show_header gives the logo 2 of 5 columns, so at the 78-column minimum it has about 31.
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
    assert "◉" in output
