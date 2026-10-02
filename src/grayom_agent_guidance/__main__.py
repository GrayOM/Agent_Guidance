"""`python -m grayom_agent_guidance`, for when the `grayom` script is not on PATH.

pipx puts `grayom` on PATH, but a source checkout or a virtualenv that was not activated does
not, and "command not found" is the first thing a new user hits. This entry point also lets
scripts/capture_screens.py drive the CLI through the interpreter it is already running.
"""

from .cli.main import app


if __name__ == "__main__":
    app()
