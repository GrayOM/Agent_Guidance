#!/usr/bin/env python3
"""Run the self-check from a source checkout.

    python scripts/design_check.py

The check itself lives in the package, as `agent-guidance self-check`, and that is the command
to use once the program is installed. This script is for a clone that has not been installed
yet, and its whole job is to fail usefully when that is the case.

It used to put `src` on sys.path and import the package directly. That makes the package
importable without making its dependencies available, so a fresh clone got
`ModuleNotFoundError: tomlkit` out of the middle of an adapter: a stack trace that reads as a
broken program and means nothing was installed. The path is still added, because running from
a checkout is the point, but the import is caught and answered with the command to run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

INSTALL = f"""
Agent Guidance is not installed in this Python, so its dependencies are missing.

  missing: {{missing}}

Install it, then run the check as a command:

  pipx install "git+https://github.com/GrayOM/Agent_Guidance.git@main"
  agent-guidance self-check

Or, to run the clone you already have, in a virtual environment:

  python -m venv .venv
  . .venv/bin/activate          # Windows: .venv\\Scripts\\Activate.ps1
  python -m pip install -e "{ROOT}"
  agent-guidance self-check
"""


def main() -> int:
    try:
        from agent_guidance.core.self_check import self_check
    except ImportError as exc:
        # ImportError, not ModuleNotFoundError: a half-installed dependency raises the parent
        # with the same cause, and a stack trace is no more useful then than it is for an
        # absent one. `name` is unset for some ImportErrors, hence the fallback.
        print(INSTALL.format(missing=exc.name or exc), file=sys.stderr)
        return 3
    return self_check()


if __name__ == "__main__":
    raise SystemExit(main())
