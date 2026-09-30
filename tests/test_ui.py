from rich.console import Console

from grayom_agent_guidance.cli.ui import LOGO, show_header


def test_logo_contains_grayom_eye_mark() -> None:
    assert "◉" in LOGO
    assert "◀" in LOGO
    assert "▶" in LOGO


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
