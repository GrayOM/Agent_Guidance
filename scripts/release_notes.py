#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for a release body.

    python scripts/release_notes.py 0.1.0

The release workflow pipes this into the GitHub release, so the notes people read are the
notes in the repository rather than a second copy written by hand that drifts from it.

Exits non-zero when the version has no section, which is what stops a tag from producing an
empty release: a version worth tagging is a version worth writing down.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def extract(version: str, changelog: str) -> str:
    """The body under `## <version>`, up to the next version heading.

    The heading carries a date (`## 0.1.0 — 2026-10-02`), so the version is matched as a whole
    token rather than as a prefix: `0.1.0` must not match `## 0.1.0rc1`, which is a different
    release that sits directly below it.
    """
    # The whole heading line is consumed, not just the version token, or the date that follows
    # it on the same line ("## 0.1.0 — 2026-10-02") becomes the first line of the body.
    start = re.search(rf"^##\s+{re.escape(version)}(?=[\s]|$).*$", changelog, flags=re.M)
    if start is None:
        raise LookupError(f"CHANGELOG.md has no section for {version}")
    rest = changelog[start.end():]
    end = re.search(r"^##\s+", rest, flags=re.M)
    body = rest[: end.start()] if end else rest
    return body.strip("\n ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the version to extract, without a leading v")
    arguments = parser.parse_args()
    try:
        print(extract(arguments.version, CHANGELOG.read_text(encoding="utf-8")))
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
