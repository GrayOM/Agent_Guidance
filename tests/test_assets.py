"""Every image the README shows has to parse.

A version of docs/assets/grayom-mark.svg shipped with a double hyphen inside an XML comment,
which XML forbids. Chromium parses SVG leniently and drew it correctly, so rendering it in a
browser -- the check that was supposed to be the careful one -- said nothing was wrong. GitHub
and other strict parsers refused the file, and the README showed a broken image.

A rendered screenshot proves how a file looks. It does not prove the file is well formed, so
that is checked here instead.
"""

import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest


ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets"
SVGS = sorted(ASSETS.glob("*.svg"))
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def test_the_assets_directory_is_not_empty() -> None:
    """Guards the parametrised tests below, which would silently pass over an empty list."""
    assert len(SVGS) >= 7


@pytest.mark.parametrize("path", SVGS, ids=lambda path: path.name)
def test_every_svg_is_well_formed_xml(path: Path) -> None:
    root = ElementTree.parse(path).getroot()
    assert root.tag == f"{{{SVG_NAMESPACE}}}svg", f"{path.name} is not an SVG document"


@pytest.mark.parametrize("path", SVGS, ids=lambda path: path.name)
def test_no_comment_carries_the_double_hyphen_xml_forbids(path: Path) -> None:
    """The specific defect, named, because the parse above only catches it by accident.

    ElementTree happens to reject it, but a parser that recovered would leave the file looking
    fine here and still broken where it is served.
    """
    text = path.read_text(encoding="utf-8")
    for start, chunk in enumerate(text.split("<!--")):
        if start == 0:
            continue
        body = chunk.split("-->")[0]
        assert "--" not in body, f"{path.name}: a comment contains a double hyphen"


@pytest.mark.parametrize("path", SVGS, ids=lambda path: path.name)
def test_no_svg_carries_executable_content(path: Path) -> None:
    """GitHub serves these under a sandbox, so this is belt and braces rather than the barrier."""
    text = path.read_text(encoding="utf-8")
    for forbidden in ("<script", "<foreignObject", "<iframe", "javascript:"):
        assert forbidden not in text, f"{path.name} contains {forbidden}"


def test_the_hand_drawn_mark_fetches_nothing() -> None:
    """Only the mark is held to this.

    The screenshots are written by Rich, whose template names the Fira Code webfont on a CDN.
    GitHub's sandbox blocks that fetch, which is why Rich also puts textLength on every run and
    why the columns still line up; stripping it would mean post-processing every capture for no
    gain. The mark is written by hand, so it has no such excuse.
    """
    text = (ASSETS / "grayom-mark.svg").read_text(encoding="utf-8")
    assert "http://" not in text.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in text
    assert "url(" not in text, "a fill referencing a definition is an indirection to go wrong"
