import re
import os
import subprocess  # nosec B404
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel

from agent_guidance.observability import redact


class ProcessTimeoutError(RuntimeError):
    pass


class ProcessResult(BaseModel):
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner:
    """Single safe entry point for child processes; shell execution is never used."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 60,
        check: bool = False,
    ) -> ProcessResult:
        if not args or not all(isinstance(value, str) and value for value in args):
            raise ValueError("process arguments must be a non-empty string list")
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            completed = subprocess.run(  # nosec B603
                list(args), cwd=cwd, env=merged_env, capture_output=True, text=True,
                timeout=timeout, check=False, shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProcessTimeoutError(f"process timed out after {timeout:g}s: {args[0]}") from exc
        result = ProcessResult(
            args=list(args), returncode=completed.returncode,
            stdout=str(redact(completed.stdout)), stderr=str(redact(completed.stderr)),
        )
        if check and result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "no process output"
            raise RuntimeError(f"process failed ({result.returncode}): {args[0]}: {detail}")
        return result


def read_version(output: str) -> str | None:
    """The version number out of a `--version` line, which each Agent formats differently.

    `codex --version` prints "codex-cli 0.160.0" and `claude --version` prints
    "2.1.287 (Claude Code)". Both were stored raw and then printed inside Agent Guidance's own
    parentheses, which read as "Codex (codex-cli 0.160.0)" and, worse, "Claude Code (2.1.287
    (Claude Code))". Only the number is wanted, so the first dotted-numeric token is taken.

    The whole stripped line is returned when there is no such token, because an unparsed
    version still tells a user more than no version at all.
    """
    match = re.search(r"\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.\-]+)?", output)
    return match.group(0) if match else (output.strip() or None)
