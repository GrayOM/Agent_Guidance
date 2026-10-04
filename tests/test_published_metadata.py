"""What a reader of the PyPI project page would actually see.

README.md refers to its screenshots and to the other documents by relative path, which is
right in a checkout and on GitHub and broken on PyPI, where there is no repository to resolve
them against. Published as-is the project page would have carried eight broken images — the
logo and every screenshot, which are the point of that page — and five links that 404.

The build rewrites those paths for the published description only. These tests read the
rewritten text out of pyproject.toml's hook configuration applied to the real README, so a
screenshot or a document added later with a relative path fails here rather than on a page
nobody checks.
"""

import re
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
RELATIVE_IMAGE = re.compile(r'<img\s+src="(?!https?:|data:)([^"]+)"')
RELATIVE_LINK = re.compile(r"\]\((?!https?:|#)([^)]+)\)")


@pytest.fixture(scope="module")
def published() -> str:
    """README.md with the configured substitutions applied, as the build publishes it."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    hook = config["tool"]["hatch"]["metadata"]["hooks"]["fancy-pypi-readme"]
    fragments = [
        (ROOT / fragment["path"]).read_text(encoding="utf-8")
        for fragment in hook["fragments"]
    ]
    text = "".join(fragments)
    for substitution in hook["substitutions"]:
        text = re.sub(substitution["pattern"], substitution["replacement"], text)
    return text


def test_the_readme_in_the_repository_stays_relative(published) -> None:
    """The file is not rewritten, only what is published.

    A reader of the repository should not be sent to raw.githubusercontent.com for a picture
    sitting next to the README.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert RELATIVE_IMAGE.search(readme), "README.md no longer uses relative image paths"
    assert published != readme


def test_the_published_description_has_no_relative_images(published) -> None:
    leftover = RELATIVE_IMAGE.findall(published)
    assert not leftover, f"these images would be broken on PyPI: {leftover}"


def test_the_published_description_has_no_relative_links(published) -> None:
    leftover = RELATIVE_LINK.findall(published)
    assert not leftover, f"these links would 404 on PyPI: {leftover}"


def test_every_screenshot_is_still_referenced(published) -> None:
    """A rewrite that silently dropped an image would pass the two tests above."""
    assets = sorted(path.name for path in (ROOT / "docs" / "assets").glob("*.svg"))
    assert assets, "no screenshots found"
    for name in assets:
        assert name in published, f"{name} is no longer referenced"


def test_the_absolute_paths_point_at_files_that_exist(published) -> None:
    """Nothing here reaches the network: the rewritten path is checked against the checkout.

    An absolute URL that 404s is no better than a relative one, and the repository is the only
    place to tell without a network call.
    """
    for url in re.findall(
        r"https://raw\.githubusercontent\.com/GrayOM/Agent_Guidance/main/(\S+?)\"", published,
    ):
        assert (ROOT / url).exists(), f"{url} is referenced but not in the repository"
    for url in re.findall(
        r"https://github\.com/GrayOM/Agent_Guidance/blob/main/([^)]+)\)", published,
    ):
        assert (ROOT / url).exists(), f"{url} is linked but not in the repository"
