#!/usr/bin/env python3
"""Capture the README's screenshots by running the real CLI.

    python scripts/capture_screens.py            # writes docs/assets/*.svg
    python scripts/capture_screens.py --check    # fails if a committed SVG is out of date

Every image in the README comes from this script, so a screenshot cannot drift from what the
program does: the SVGs it replaced were drawn by hand and showed a menu that no longer existed.

How it works, and why it is not simpler: the interview and the menu are InquirerPy prompts,
which refuse to run without a TTY and redraw themselves with cursor movement. So each screen
is driven through a pty with scripted keystrokes, the output is fed to a VT100 emulator
(pyte) to get the screen as it actually looks, and that buffer is rendered to SVG with Rich.
Appending the raw output instead would show every intermediate redraw stacked on top of itself.

Keystrokes are written as readable names in SCREENS below. Nothing here touches the real
HOME: each capture runs against a throwaway directory, so the screenshots show a first run.
"""

from __future__ import annotations

import argparse
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pyte
from rich.console import Console
from rich.segment import Segment
from rich.style import Style
from rich.terminal_theme import TerminalTheme


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
COLUMNS, LINES = 96, 34
# The plan is longer than a default terminal, and a screen that scrolls loses its top: the
# first capture of it showed only the security panel. Each screen may ask for more rows.
PLAN_LINES = 140
# How long a silence has to last before the capture gives up and says so, rather than
# writing out whatever happened to be on screen.
MAX_IDLE = 30.0

KEYS = {
    "enter": "\r",
    "space": " ",
    "down": "\x1b[B",
    "up": "\x1b[A",
    "ctrl-c": "\x03",
    "q": "q",
    "n": "n",
    "y": "y",
}

# A GitHub-dark palette, so the SVG reads the same in both of GitHub's themes rather than
# relying on a background the page may not provide.
THEME = TerminalTheme(
    (13, 17, 23), (201, 209, 217),
    [(72, 79, 88), (255, 123, 114), (63, 185, 80), (210, 153, 34),
     (88, 166, 255), (188, 140, 255), (57, 197, 207), (176, 185, 196)],
    [(110, 118, 129), (255, 163, 152), (86, 211, 100), (227, 179, 65),
     (121, 192, 255), (210, 168, 255), (86, 216, 226), (255, 255, 255)],
)


def _render(
    screen: pyte.Screen, title: str, out: Path, rows: tuple[int, int] | None = None,
) -> None:
    """Turn the emulator's screen buffer into an SVG, one styled segment per run of cells.

    `rows` takes a window out of a screen too tall to read as one image. The plan is ~100
    lines, and GitHub scales a single image of it down to nothing, so it ships as two.
    """
    console = Console(record=True, width=COLUMNS, file=open(os.devnull, "w"))
    segments: list[Segment] = []
    filled = [index for index in range(screen.lines) if screen.buffer.get(index)]
    first, last = 0, (max(filled) if filled else 0)
    if rows:
        first, last = rows[0], min(rows[1], last)
    for index in range(first, last + 1):
        row = screen.buffer.get(index, {})
        text, style = "", None
        for column in range(screen.columns):
            cell = row.get(column)
            char = cell.data if cell and cell.data else " "
            current = _style(cell) if cell else Style()
            if style is not None and current != style:
                segments.append(Segment(text, style))
                text = ""
            style, text = current, text + char
        segments.append(Segment(text.rstrip() or " ", style))
        segments.append(Segment("\n"))
    console._record_buffer = segments
    # Rich's own template, unchanged. A trimmed-down one here dropped the translate and
    # clip-path around the character matrix, which let the text sit over the window chrome.
    # Rich puts textLength on every run, so columns stay aligned on GitHub, where the
    # template's Fira Code webfont cannot load and a fallback metric is used instead.
    out.write_text(console.export_svg(title=title, theme=THEME))


# pyte and Rich disagree on three points: pyte calls yellow "brown", spells the bright
# variants without a separator, and returns bare hex for the 256-colour range.
PYTE_COLOURS = {
    "brown": "yellow",
    **{f"bright{name}": f"bright_{name}" for name in
       ("black", "red", "green", "blue", "magenta", "cyan", "white")},
    "brightbrown": "bright_yellow",
}


def _style(cell) -> Style:
    def colour(value: str) -> str | None:
        if value in {"default", ""}:
            return None
        if re.fullmatch(r"[0-9a-fA-F]{6}", value):
            return f"#{value}"
        return PYTE_COLOURS.get(value, value)

    return Style(
        color=colour(cell.fg), bgcolor=colour(cell.bg),
        bold=cell.bold, italic=cell.italics, underline=cell.underscore, reverse=cell.reverse,
    )


# An InquirerPy prompt draws a pointer at the row the cursor is on, and erases the whole list
# once answered, leaving a one-line summary behind. So the pointer is on screen exactly while a
# question is waiting for an answer, whatever that question's wording or punctuation.
#
# The first version of this matched "? <question>:" instead, on the assumption that every
# question ends in a colon. The menu asks "What would you like to do?", so it never matched,
# and the menu screen was only ever captured because the loop also stopped on a timer.
_POINTER = "❯"


def _waiting_for_input(screen: pyte.Screen) -> bool:
    return any(line.strip().startswith(_POINTER) for line in screen.display)


def _drive(
    arguments: list[str], keys: list[str], home: Path, settle: float, lines: int = LINES,
) -> pyte.Screen:
    """Run one command in a pty, send the keystrokes, return the final screen."""
    screen = pyte.Screen(COLUMNS, lines)
    stream = pyte.Stream(screen)
    master, slave = pty.openpty()
    environment = {
        **os.environ,
        "HOME": str(home), "USERPROFILE": str(home),
        "TERM": "xterm-256color", "COLUMNS": str(COLUMNS), "LINES": str(lines),
        "FORCE_COLOR": "1", "NO_COLOR": "", "PYTHONUNBUFFERED": "1",
        # prompt_toolkit asks the terminal for its cursor position once per prompt and
        # prints "your terminal doesn't support cursor position requests (CPR)" across the
        # screen if no answer arrives in two seconds. Replying from this loop won one race
        # and lost the next, so the request is turned off at its documented switch instead.
        "PROMPT_TOOLKIT_NO_CPR": "1",
        # The screenshots must not depend on a token, a network reply or a cached result.
        "GITHUB_TOKEN": "", "GH_TOKEN": "", "GRAYOM_HOME": str(home / ".grayom"),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "grayom_agent_guidance", *arguments],
        stdin=slave, stdout=slave, stderr=slave, env=environment, cwd=ROOT, close_fds=True,
    )
    os.close(slave)
    pending = list(keys)
    quiet = 0.0
    deadline = time.monotonic() + 180
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], 0.2)
            if readable:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                stream.feed(chunk.decode("utf-8", "replace"))
                continue
            # Quiet for 200ms. That is not enough on its own to mean "waiting for input":
            # start-up detects the Agents by running `codex --version` and `claude --version`,
            # which is a silent second with no prompt on screen. A key sent into that gap is
            # discarded, because the first prompt_toolkit Application drains the input buffer
            # as it starts, and the terminal echoed the raw escape sequence into the capture.
            if pending and _waiting_for_input(screen):
                os.write(master, KEYS[pending.pop(0)].encode())
                quiet = 0.0
                continue
            quiet += 0.2
            # The capture is finished when the program has nothing left to say, and silence
            # alone does not establish that. An earlier version waited a fixed `settle` and
            # stopped; start-up runs `codex --version` and `claude --version` before printing
            # anything else, and once that pause grew past the guess the menu screen captured
            # as the header alone. So stop only on a reason: the process ended, or a question
            # is on screen with no keys left to answer it.
            if process.poll() is not None:
                break
            if not pending and _waiting_for_input(screen) and quiet >= settle:
                break
            if quiet >= MAX_IDLE:
                raise SystemExit(
                    f"{' '.join(arguments) or 'grayom'}: nothing happened for {MAX_IDLE:.0f}s "
                    f"and no prompt appeared; {len(pending)} keystrokes were left unsent"
                )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        os.close(master)
    return screen


# Each entry is one README image. 'keys' stops at the screen being photographed: a capture
# that ran to completion would show the result, not the question.
#
# The counts below are positions in real option lists, so they are checked rather than guessed:
# tests/test_capture_screens.py asserts each index still names the option the README describes.
# Both detected Agents arrive pre-selected, so the first 'enter' accepts them; a 'space' there
# would clear one, which is what the first version of this file did by accident.
SECURITY_DOMAIN = 6     # "Penetration testing and assessment" in the domain list
OSINT_DOMAIN = 7        # "OSINT", the row below it
ASSESSMENT_TASKS = (0, 1, 3)  # web application, authentication, injection

SCREENS: list[dict] = [
    {
        "name": "menu",
        "title": "grayom",
        "arguments": [],
        "keys": [],
        "settle": 0.6,
    },
    {
        "name": "interview-domains",
        "title": "grayom  -  choose your work",
        "arguments": ["recommend", "--offline"],
        "keys": [
            "enter",
            *["down"] * SECURITY_DOMAIN, "space",
            "down", "space",
        ],
        "settle": 0.6,
    },
    {
        "name": "interview-tasks",
        "title": "grayom  -  choose your work",
        "arguments": ["recommend", "--offline"],
        "keys": [
            "enter",
            *["down"] * SECURITY_DOMAIN, "space", "enter",
            "space", "down", "space", "down", "down", "space",
        ],
        "settle": 0.6,
    },
    {
        "name": "plan",
        # One run, two images: a capture takes about half a minute, and the plan is too tall to
        # read as a single picture once GitHub scales it to the width of the page.
        "images": [
            {"name": "plan", "title": "grayom recommend", "rows": (16, 65)},
            {"name": "plan-approval", "title": "grayom recommend  -  what will change",
             "rows": (66, 104)},
        ],
        "arguments": ["recommend", "--offline"],
        "keys": [
            "enter",
            # Both security domains, so the plan has to reconcile two sets of capabilities.
            *["down"] * SECURITY_DOMAIN, "space", "down", "space", "enter",
            # Assessment tasks, then the OSINT list the second domain opens.
            "space", "down", "space", "down", "down", "space", "enter",
            "space", "down", "space", "enter",
            # Performance rather than Minimal: Minimal is the right default but installs the
            # smallest set, which made the screenshot of the plan read as an empty plan.
            "down", "enter",
        ],
        "settle": 2.5,
        "lines": PLAN_LINES,
    },
    {
        "name": "doctor",
        "title": "grayom doctor",
        "arguments": ["doctor"],
        "keys": [],
        "settle": 1.0,
    },
    {
        "name": "help",
        "title": "grayom --help",
        "arguments": ["--help"],
        "keys": [],
        "settle": 0.4,
    },
]


def capture(destination: Path, only: str | None = None, as_text: bool = False) -> list[Path]:
    written = []
    for screen in SCREENS:
        if only and screen["name"] != only:
            continue
        with tempfile.TemporaryDirectory(prefix="grayom-capture-") as name:
            home = Path(name).resolve()
            buffer = _drive(
                screen["arguments"], screen["keys"], home, screen["settle"],
                lines=screen.get("lines", LINES),
            )
        if as_text:
            # The screen exactly as the emulator holds it: the only honest way to check a
            # keystroke sequence landed on the screen it was meant to photograph.
            print(f"\n===== {screen['name']} =====")
            print("\n".join(line.rstrip() for line in buffer.display).rstrip())
            continue
        filled = sum(1 for index in range(buffer.lines) if buffer.buffer.get(index))
        if filled < 3:
            raise SystemExit(f"{screen['name']}: captured a blank screen")
        images = screen.get("images") or [
            {"name": screen["name"], "title": screen["title"], "rows": screen.get("rows")}
        ]
        for image in images:
            out = destination / f"{image['name']}.svg"
            _render(buffer, image["title"], out, rows=image.get("rows"))
            print(f"  {out.name:28} {filled:>3} rows captured")
            written.append(out)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="compare against the committed SVGs instead of overwriting them",
    )
    parser.add_argument("--only", help="capture one screen by name")
    parser.add_argument(
        "--text", action="store_true",
        help="print the captured screens as plain text and write nothing",
    )
    arguments = parser.parse_args()

    if arguments.text:
        capture(ASSETS, only=arguments.only, as_text=True)
        return 0

    if arguments.check:
        with tempfile.TemporaryDirectory(prefix="grayom-check-") as name:
            fresh = Path(name)
            print("capturing screens for comparison")
            stale = [
                path.name for path in capture(fresh)
                if not (ASSETS / path.name).exists()
                or (ASSETS / path.name).read_text() != path.read_text()
            ]
        if stale:
            print("\nout of date: " + ", ".join(sorted(stale)))
            print("run: python scripts/capture_screens.py")
            return 1
        print("\nevery screenshot matches the current CLI")
        return 0

    ASSETS.mkdir(parents=True, exist_ok=True)
    print(f"capturing screens into {ASSETS.relative_to(ROOT)}")
    capture(ASSETS, only=arguments.only)
    return 0


if __name__ == "__main__":
    if shutil.which("git") is None:
        raise SystemExit("git is required: the offline Registry clones pinned repositories")
    raise SystemExit(main())
