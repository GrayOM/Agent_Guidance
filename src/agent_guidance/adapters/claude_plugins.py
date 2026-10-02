"""Install Claude Code plugins through Claude Code's own plugin commands.

A plugin is not a settings key. Verified against an installed Claude Code: enabling one in
`settings.json` only toggles a plugin that is already installed, while installing it adds a
marketplace, fetches the plugin's archive, validates its manifest and materialises it under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. The install can also run a
command the marketplace declares, which Claude Code gates behind showing that command and
its sha256 to a person.

Reimplementing that would mean reimplementing Claude Code's plugin trust model, so Agent Guidance
delegates it and wraps a transaction around it instead. The delegation is reversible because
each step has an inverse that restores the previous state exactly:

| step                   | inverse                      |
|------------------------|------------------------------|
| `marketplace add`      | `marketplace remove`         |
| `plugin install`       | `plugin uninstall`           |

Every command is asked for `--json` so the outcome is read rather than inferred from text,
and `--yes` / `--accept-command` are never passed: a marketplace-declared command is the
user's decision, so a plugin needing one is reported and skipped rather than accepted on
their behalf.
"""

import json
import shutil
from typing import Any

from agent_guidance.runtime import ProcessRunner

from .codex import AdapterError


# Passing either of these would accept a marketplace-declared command on the user's behalf.
FORBIDDEN_FLAGS = frozenset({"-y", "--yes", "--accept-command"})

COMMAND_APPROVAL_HINT = (
    "this plugin's marketplace declares a command that Claude Code must show you before it "
    "runs; install it yourself with: claude plugin install"
)


class PluginCliUnavailable(AdapterError):
    """Claude Code's CLI is not on PATH, so plugins cannot be installed or inspected."""


class ClaudePluginCli:
    """The only place Agent Guidance runs `claude plugin`."""

    def __init__(self, executable: str | None = None, timeout: float = 120) -> None:
        self._executable = executable
        self.timeout = timeout

    @property
    def executable(self) -> str | None:
        return self._executable or shutil.which("claude")

    @property
    def available(self) -> bool:
        return self.executable is not None

    def _run(self, *arguments: str) -> dict[str, Any] | list[Any]:
        forbidden = FORBIDDEN_FLAGS.intersection(arguments)
        if forbidden:
            raise AdapterError(
                f"refusing to pass {', '.join(sorted(forbidden))} to Claude Code: a "
                "marketplace-declared command is the user's decision"
            )
        executable = self.executable
        if executable is None:
            raise PluginCliUnavailable(
                "the claude executable is required to manage Claude Code plugins"
            )
        command = [executable, "plugin", *arguments, "--json"]
        try:
            result = ProcessRunner().run(command, timeout=self.timeout)
        except FileNotFoundError as exc:
            raise PluginCliUnavailable("the claude executable disappeared mid-run") from exc
        except RuntimeError as exc:
            raise AdapterError(str(exc)) from exc
        return self._parse(result.stdout, result.stderr, result.returncode, arguments)

    @staticmethod
    def _parse(
        stdout: str, stderr: str, returncode: int, arguments: tuple[str, ...],
    ) -> dict[str, Any] | list[Any]:
        """Read the JSON result out of stdout, which may also carry progress lines.

        `claude plugin list --json` pretty-prints its array over many lines, so reading one
        line at a time finds nothing; other commands print progress text before their result.
        Each line that starts a JSON value is therefore decoded and the document reaching
        furthest through the output wins, which is the outer array rather than the first
        object nested inside it.
        """
        decoder = json.JSONDecoder()
        best: tuple[int, dict[str, Any] | list[Any]] | None = None
        offset = 0
        for line in stdout.splitlines(keepends=True):
            start = offset + (len(line) - len(line.lstrip()))
            offset += len(line)
            if stdout[start:start + 1] not in {"[", "{"}:
                continue
            try:
                value, end = decoder.raw_decode(stdout, start)
            except ValueError:
                continue
            if isinstance(value, (dict, list)) and (best is None or end > best[0]):
                best = (end, value)
        if best is not None:
            return best[1]
        detail = (stderr.strip() or stdout.strip() or "no output")[:400]
        raise AdapterError(
            f"claude plugin {' '.join(arguments)} returned no JSON result "
            f"(exit {returncode}): {detail}"
        )

    # --- reading -------------------------------------------------------------------

    def installed(self) -> dict[str, dict[str, Any]]:
        """Installed plugins by id. An entry without an installPath is not installed."""
        payload = self._run("list")
        if not isinstance(payload, list):
            raise AdapterError("claude plugin list did not return a list")
        return {
            str(item["id"]): item for item in payload
            if isinstance(item, dict) and item.get("id") and item.get("installPath")
        }

    def marketplaces(self) -> set[str]:
        payload = self._run("marketplace", "list")
        if not isinstance(payload, list):
            raise AdapterError("claude plugin marketplace list did not return a list")
        return {str(item["name"]) for item in payload if isinstance(item, dict) and item.get("name")}

    # --- writing -------------------------------------------------------------------

    @staticmethod
    def _require_ok(payload: dict[str, Any] | list[Any], action: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AdapterError(f"{action} returned an unexpected result")
        if payload.get("outcome") != "ok":
            message = str(payload.get("message") or payload.get("error") or payload)[:400]
            if "command" in message.lower() and "accept" in message.lower():
                raise AdapterError(f"{action} needs approval: {COMMAND_APPROVAL_HINT}")
            raise AdapterError(f"{action} failed: {message}")
        return payload

    def add_marketplace(self, source: str, scope: str = "user") -> str:
        payload = self._require_ok(
            self._run("marketplace", "add", source, "--scope", scope),
            f"adding marketplace {source}",
        )
        name = payload.get("marketplace")
        if not name:
            raise AdapterError(f"adding marketplace {source} reported no marketplace name")
        return str(name)

    def remove_marketplace(self, name: str, scope: str = "user") -> None:
        self._require_ok(
            self._run("marketplace", "remove", name, "--scope", scope),
            f"removing marketplace {name}",
        )

    def install(self, plugin_id: str, scope: str = "user") -> str:
        payload = self._require_ok(
            self._run("install", plugin_id, "--scope", scope), f"installing {plugin_id}",
        )
        return str(payload.get("pluginId") or plugin_id)

    def uninstall(self, plugin_id: str, scope: str = "user") -> None:
        self._require_ok(
            self._run("uninstall", plugin_id, "--scope", scope), f"uninstalling {plugin_id}",
        )
