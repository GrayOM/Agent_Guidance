from rich.console import Console

from grayom_agent_guidance.cli.ui import LOGO, show_header


def test_logo_is_ascii_only_and_identifies_grayom() -> None:
    assert LOGO.isascii()
    assert "####" in LOGO\n    assert "G R A Y O M" not in LOGO


def test_header_prints_product_name() -> None:
    console = Console(record=True, color_system=None, width=100)
    show_header(console)

    output = console.export_text()
    assert "G R A Y O M" in output
    assert "GrayOM Agent Guidance" in output\n    assert "AI Agent Environment Manager" in output
