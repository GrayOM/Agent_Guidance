"""Claude Code plugin support: discovery of a marketplace, install, health, rollback.

Every JSON shape asserted here was recorded from a real `claude plugin ... --json` run
against an installed Claude Code in an isolated HOME, not inferred from documentation.
"""

import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from grayom_agent_guidance.adapters import ClaudeCodeAdapter
from grayom_agent_guidance.adapters.claude_plugins import (
    COMMAND_APPROVAL_HINT, ClaudePluginCli, PluginCliUnavailable,
)
from grayom_agent_guidance.adapters.codex import AdapterError
from grayom_agent_guidance.core.compatibility import evaluate_compatibility
from grayom_agent_guidance.models import (
    AgentInstallation, AgentType, Capability, CompatibilityStatus, Component, ComponentType,
    InstallKind, InstallMethod, SourceType,
)
from grayom_agent_guidance.sources.base import RawCandidate
from grayom_agent_guidance.sources.github import _file_priority
from grayom_agent_guidance.sources.normalizer import normalize_candidate
from grayom_agent_guidance.sources.validator import ComponentValidator


MARKETPLACE_PATH = ".claude-plugin/marketplace.json"


def marketplace(*plugins: dict[str, str], name: str = "grayom-lab") -> str:
    return json.dumps({
        "name": name, "owner": {"name": "GrayOM"},
        "plugins": [{"source": f"./plugins/{item['name']}", **item} for item in plugins],
    })


def raw_marketplace_repository(manifest: str, extra_paths: list[str] | None = None) -> RawCandidate:
    return RawCandidate(
        repository_full_name="example/lab", repository_url="https://github.com/example/lab",
        source_type=SourceType.GITHUB, source_version="2026-09-01T00:00:00Z",
        metadata={
            "name": "lab", "description": "Claude Code plugins for source code analysis",
            "stargazers_count": 40, "pushed_at": "2026-09-01T00:00:00Z",
            "license": {"spdx_id": "MIT"}, "head_sha": "deadbee", "default_branch": "main",
        },
        readme="Claude Code plugin marketplace for source code analysis.",
        tree_paths=[MARKETPLACE_PATH, *(extra_paths or [])],
        files={MARKETPLACE_PATH: manifest},
    )


# --- discovery -----------------------------------------------------------------------


def test_marketplace_repository_becomes_an_installable_plugin() -> None:
    component = normalize_candidate(raw_marketplace_repository(
        marketplace({"name": "sast", "description": "static analysis of source code"})
    ))

    assert component.type == ComponentType.PLUGIN
    assert component.install_method.kind == InstallKind.PLUGIN_MARKETPLACE
    assert component.install_method.plugin_id == "sast@grayom-lab"
    assert component.install_method.marketplace == "grayom-lab"
    assert component.install_method.marketplace_source == "https://github.com/example/lab"
    assert AgentType.CLAUDE_CODE in component.supported_agents

    validated = ComponentValidator({AgentType.CLAUDE_CODE}).validate(component)
    assert validated.recommendable, validated.validation_warnings
    assert evaluate_compatibility(
        validated,
        AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True),
    ).status == CompatibilityStatus.SUPPORTED


def test_plugin_without_a_marketplace_is_refused_with_a_stated_reason() -> None:
    """A bare plugin.json has no install path GrayOM can take or reverse.

    Claude Code fetches a plugin through a marketplace, so a repository that only declares a
    plugin manifest is recorded as PLUGIN_GIT and rejected by name, rather than appearing on
    the Plan as something that would fail at install time.
    """
    raw = RawCandidate(
        repository_full_name="example/plug", repository_url="https://github.com/example/plug",
        source_type=SourceType.GITHUB,
        metadata={"name": "plug", "description": "Claude Code source code analysis plugin"},
        readme="Claude Code plugin for code analysis.", tree_paths=["plugin.json"],
    )
    component = ComponentValidator({AgentType.CLAUDE_CODE}).validate(normalize_candidate(raw))

    assert component.install_method.kind == InstallKind.PLUGIN_GIT
    assert not component.recommendable
    assert any("marketplace" in warning for warning in component.validation_warnings)
    assert evaluate_compatibility(
        component, AgentInstallation(agent=AgentType.CLAUDE_CODE, detected=True),
    ).status == CompatibilityStatus.PARTIAL


def test_a_marketplace_does_not_reclassify_a_skill_repository() -> None:
    """Skill repositories keep the bounded selection that caps their context cost.

    Installing such a repository as a plugin would load every Skill it bundles, which is
    exactly what core.skill_selection exists to prevent.
    """
    component = normalize_candidate(raw_marketplace_repository(
        marketplace({"name": "sast", "description": "static analysis"}),
        extra_paths=["skills/review/SKILL.md"],
    ))

    assert component.type == ComponentType.SKILL
    assert component.install_method.kind == InstallKind.GIT_SKILLS


def test_multi_plugin_marketplace_picks_the_closest_match_and_says_which() -> None:
    component = normalize_candidate(raw_marketplace_repository(marketplace(
        {"name": "notes", "description": "scratch pad"},
        {"name": "auditor", "description": "static analysis and vulnerability research for code review"},
    )))

    assert component.install_method.plugin_id == "auditor@grayom-lab"
    assert any(
        "declares 2 plugins" in warning and "auditor" in warning
        for warning in component.validation_warnings
    ), component.validation_warnings


def test_a_malformed_marketplace_manifest_does_not_pass_as_installable() -> None:
    component = normalize_candidate(raw_marketplace_repository("{ not json"))

    assert component.type == ComponentType.PLUGIN
    assert component.install_method.kind == InstallKind.PLUGIN_GIT


def test_manifests_are_read_before_the_per_repository_file_budget_runs_out() -> None:
    """An anonymous run may only read four files, so the decisive ones go first.

    Without this the tree order decided it, and a repository listing package.json and a
    Dockerfile first spent its whole budget before reaching the manifest that says whether
    the repository is installable at all.
    """
    paths = [
        "package.json", "Dockerfile", "requirements.txt", "install.sh",
        ".claude-plugin/marketplace.json", "pyproject.toml",
    ]

    assert sorted(paths, key=_file_priority)[:2] == [".claude-plugin/marketplace.json", "install.sh"]


# --- the CLI wrapper -----------------------------------------------------------------


def fake_claude(
    tmp_path: Path, stdout: str = "", *, noise: str = "", stderr: str = "", exit_code: int = 0,
) -> ClaudePluginCli:
    """A stand-in `claude` that records its arguments, so command shape is tested for real.

    The stub is a Python file behind a platform-appropriate launcher. A `#!` script is not
    executable on Windows, and the launcher embeds this interpreter's own path rather than
    trusting whatever `python` resolves to on the runner.
    """
    stub = tmp_path / "claude_stub.py"
    stub.write_text(
        "import sys\n"
        f"open({str(tmp_path / 'calls.txt')!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10))\n"
        f"sys.stdout.write({noise!r})\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    if sys.platform == "win32":
        launcher = tmp_path / "claude.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8",
        )
    else:
        launcher = tmp_path / "claude"
        launcher.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(stub))} "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return ClaudePluginCli(executable=str(launcher))


def recorded_calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.txt"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_cli_asks_for_json_and_reads_the_machine_readable_line(tmp_path) -> None:
    cli = fake_claude(tmp_path, "[]\n", noise="Fetching marketplaces...\n")

    assert cli.marketplaces() == set()
    assert recorded_calls(tmp_path) == ["plugin marketplace list --json"]


def test_a_pretty_printed_array_is_read_as_one_document(tmp_path) -> None:
    """`claude plugin list --json` indents its array over many lines.

    Reading one line at a time found no JSON at all and reported a working Claude Code as
    broken, after the plugin had already been installed. Taking the document that reaches
    furthest also keeps the outer array from being mistaken for the first object inside it.
    """
    cli = fake_claude(
        tmp_path,
        json.dumps([{"id": "sast@lab", "installPath": "/cache/sast", "enabled": True}], indent=2),
        noise="Loading plugins...\n",
    )

    assert set(cli.installed()) == {"sast@lab"}


def test_an_entry_without_an_install_path_is_not_reported_as_installed(tmp_path) -> None:
    """Claude Code lists a failed plugin with an empty installPath and an errors field."""
    cli = fake_claude(tmp_path, json.dumps([
        {"id": "broken@lab", "installPath": "", "errors": ["manifest invalid"], "enabled": False},
        {
            "id": "sast@lab", "installPath": "/home/u/.claude/plugins/cache/lab/sast/0.1.0",
            "enabled": True, "version": "0.1.0", "scope": "user",
        },
    ]))

    assert set(cli.installed()) == {"sast@lab"}


def test_forbidden_flags_are_never_passed_to_claude(tmp_path) -> None:
    """`--yes` and `--accept-command` accept a marketplace-declared command for the user."""
    cli = fake_claude(tmp_path, json.dumps({"outcome": "ok"}))

    with pytest.raises(AdapterError, match="--yes"):
        cli._run("install", "sast@lab", "--yes")
    assert recorded_calls(tmp_path) == [], "the refusal happens before claude is run"


def test_a_missing_executable_is_its_own_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("grayom_agent_guidance.adapters.claude_plugins.shutil.which", lambda _: None)
    with pytest.raises(PluginCliUnavailable):
        ClaudePluginCli().installed()


def test_output_without_json_is_reported_with_what_claude_actually_said(tmp_path) -> None:
    cli = fake_claude(tmp_path, stderr="not logged in", exit_code=1)

    with pytest.raises(AdapterError, match="not logged in"):
        cli.installed()


def test_a_plugin_needing_command_approval_is_handed_back_to_the_user(tmp_path) -> None:
    cli = fake_claude(tmp_path, json.dumps({
        "outcome": "error", "message": "Plugin declares a command; accept it to continue",
    }))

    with pytest.raises(AdapterError) as error:
        cli.install("sast@lab")
    assert COMMAND_APPROVAL_HINT in str(error.value)


def test_the_real_mutation_commands_carry_the_scope_and_the_json_flag(tmp_path) -> None:
    """These are the two commands that change the user's machine, so their shape is asserted."""
    cli = fake_claude(tmp_path, json.dumps({"outcome": "ok", "marketplace": "grayom-lab"}))

    assert cli.add_marketplace("https://github.com/example/lab") == "grayom-lab"
    cli.remove_marketplace("grayom-lab")
    cli.uninstall("sast@grayom-lab")

    assert recorded_calls(tmp_path) == [
        "plugin marketplace add https://github.com/example/lab --scope user --json",
        "plugin marketplace remove grayom-lab --scope user --json",
        "plugin uninstall sast@grayom-lab --scope user --json",
    ]


def test_an_ok_that_names_no_marketplace_is_not_treated_as_success(tmp_path) -> None:
    """Without the name, rollback would have nothing to remove."""
    cli = fake_claude(tmp_path, json.dumps({"outcome": "ok"}))

    with pytest.raises(AdapterError, match="no marketplace name"):
        cli.add_marketplace("https://github.com/example/lab")


def test_install_returns_the_id_claude_actually_used(tmp_path) -> None:
    cli = fake_claude(tmp_path, json.dumps({"outcome": "ok", "pluginId": "sast@grayom-lab"}))

    assert cli.install("sast@grayom-lab") == "sast@grayom-lab"


def test_a_reading_command_that_returns_an_object_is_rejected(tmp_path) -> None:
    """A dict where a list belongs means the output is not what this code was written against."""
    cli = fake_claude(tmp_path, json.dumps({"outcome": "ok"}))

    with pytest.raises(AdapterError, match="did not return a list"):
        cli.installed()
    with pytest.raises(AdapterError, match="did not return a list"):
        cli.marketplaces()


# --- the adapter ---------------------------------------------------------------------


class StubCli(ClaudePluginCli):
    """Records calls in order so install and rollback sequencing can be asserted."""

    def __init__(
        self,
        installed: dict[str, dict[str, Any]] | None = None,
        marketplaces: set[str] | None = None,
        install_succeeds: bool = True,
    ) -> None:
        super().__init__(executable="/usr/bin/claude")
        self._installed = dict(installed or {})
        self._marketplaces = set(marketplaces or set())
        self._install_succeeds = install_succeeds
        self.calls: list[tuple[str, str]] = []

    def installed(self) -> dict[str, dict[str, Any]]:
        return dict(self._installed)

    def marketplaces(self) -> set[str]:
        return set(self._marketplaces)

    def add_marketplace(self, source: str, scope: str = "user") -> str:
        self.calls.append(("marketplace add", source))
        self._marketplaces.add("grayom-lab")
        return "grayom-lab"

    def remove_marketplace(self, name: str, scope: str = "user") -> None:
        self.calls.append(("marketplace remove", name))
        self._marketplaces.discard(name)

    def install(self, plugin_id: str, scope: str = "user") -> str:
        self.calls.append(("install", plugin_id))
        if self._install_succeeds:
            self._installed[plugin_id] = {"installPath": "/cache/sast", "enabled": True}
        return plugin_id

    def uninstall(self, plugin_id: str, scope: str = "user") -> None:
        self.calls.append(("uninstall", plugin_id))
        self._installed.pop(plugin_id, None)


def plugin_component() -> Component:
    return Component(
        id="example-lab", name="lab", type=ComponentType.PLUGIN,
        github_url="https://github.com/example/lab",
        supported_agents={AgentType.CLAUDE_CODE}, capabilities={Capability.SOURCE_ANALYSIS},
        install_method=InstallMethod(
            kind=InstallKind.PLUGIN_MARKETPLACE, plugin_id="sast@grayom-lab",
            marketplace="grayom-lab", marketplace_source="https://github.com/example/lab",
        ),
    )


def test_install_adds_the_marketplace_then_the_plugin_and_records_both(tmp_path) -> None:
    cli = StubCli()
    result = ClaudeCodeAdapter(tmp_path, plugins=cli).install_plugin(plugin_component())

    assert cli.calls == [
        ("marketplace add", "https://github.com/example/lab"),
        ("install", "sast@grayom-lab"),
    ]
    assert result.added_marketplaces == ["grayom-lab"]
    assert result.installed_plugins == ["sast@grayom-lab"]
    assert result.changed


def test_a_marketplace_the_user_already_had_is_not_recorded_as_ours(tmp_path) -> None:
    """Rollback must not remove a marketplace this run did not add."""
    cli = StubCli(marketplaces={"grayom-lab"})
    result = ClaudeCodeAdapter(tmp_path, plugins=cli).install_plugin(plugin_component())

    assert cli.calls == [("install", "sast@grayom-lab")]
    assert result.added_marketplaces == []


def test_an_already_installed_plugin_is_preserved(tmp_path) -> None:
    cli = StubCli(installed={"sast@grayom-lab": {"installPath": "/cache/sast", "enabled": True}})
    result = ClaudeCodeAdapter(tmp_path, plugins=cli).install_plugin(plugin_component())

    assert cli.calls == []
    assert not result.changed
    assert result.installed_plugins == []
    assert any("preserved" in note for note in result.notes)


def test_install_fails_when_claude_does_not_list_the_plugin_afterwards(tmp_path) -> None:
    """An `outcome: ok` that left nothing installed is a failure, not a success."""
    cli = StubCli(install_succeeds=False)

    with pytest.raises(AdapterError, match="does not list it as installed"):
        ClaudeCodeAdapter(tmp_path, plugins=cli).install_plugin(plugin_component())


def test_a_git_only_plugin_is_refused_by_the_adapter_too(tmp_path) -> None:
    component = plugin_component()
    component.install_method = InstallMethod(
        kind=InstallKind.PLUGIN_GIT, repository="https://github.com/example/lab",
    )

    with pytest.raises(AdapterError, match="marketplace"):
        ClaudeCodeAdapter(tmp_path, plugins=StubCli()).install_plugin(component)


def test_rollback_removes_the_plugin_before_the_marketplace(tmp_path) -> None:
    """A marketplace cannot be removed while a plugin installed from it is still there."""
    adapter = ClaudeCodeAdapter(tmp_path, plugins=StubCli())
    manifest = adapter.backup(tmp_path / "backup")
    from grayom_agent_guidance.models import InstallationManifest

    installation = InstallationManifest(backup=manifest)
    installation.record(adapter.install_plugin(plugin_component()))
    cli = adapter.plugins
    assert isinstance(cli, StubCli)
    cli.calls.clear()

    result = adapter.rollback(installation)

    assert cli.calls == [
        ("uninstall", "sast@grayom-lab"), ("marketplace remove", "grayom-lab"),
    ]
    assert not result.errors


def test_a_marketplace_registered_under_another_name_retargets_the_install(tmp_path) -> None:
    """Claude Code names the marketplace from its own manifest, not from the URL.

    The plugin id has to follow that name, or the install would ask for a marketplace that is
    not registered.
    """

    class Renaming(StubCli):
        def add_marketplace(self, source: str, scope: str = "user") -> str:
            self.calls.append(("marketplace add", source))
            self._marketplaces.add("upstream-name")
            return "upstream-name"

    cli = Renaming()
    result = ClaudeCodeAdapter(tmp_path, plugins=cli).install_plugin(plugin_component())

    assert ("install", "sast@upstream-name") in cli.calls
    assert result.installed_plugins == ["sast@upstream-name"]
    assert any("upstream-name" in note for note in result.notes)


def test_health_check_separates_installed_from_merely_enabled(tmp_path) -> None:
    component = plugin_component()
    cli = StubCli(installed={"sast@grayom-lab": {"installPath": "/cache/sast", "enabled": False}})
    checks = {
        check.name: check
        for check in ClaudeCodeAdapter(tmp_path, plugins=cli).health_check([component]).checks
    }

    assert checks["claude_plugin_installed:sast@grayom-lab"].passed
    enabled = checks["claude_plugin_enabled:sast@grayom-lab"]
    assert not enabled.passed and not enabled.fatal, "switched off is a warning, not a failure"


def test_health_check_fails_when_the_plugin_is_not_installed(tmp_path) -> None:
    result = ClaudeCodeAdapter(tmp_path, plugins=StubCli()).health_check([plugin_component()])
    failed = [check for check in result.checks if not check.passed and check.fatal]

    assert any(check.name == "claude_plugin_installed:sast@grayom-lab" for check in failed)


def test_listing_plugins_falls_back_to_settings_when_the_cli_is_unavailable(tmp_path) -> None:
    """`enabledPlugins` is the only record left when `claude` cannot be run."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"enabledPlugins": {"sast@grayom-lab": True}}), encoding="utf-8")

    class Unavailable(StubCli):
        def installed(self) -> dict[str, dict[str, Any]]:
            raise PluginCliUnavailable("claude is not installed")

    adapter = ClaudeCodeAdapter(tmp_path, plugins=Unavailable())
    assert adapter.list_existing_plugins() == ["sast@grayom-lab"]
    assert os.path.exists(settings)


def test_the_install_summary_names_the_plugin_and_the_marketplace() -> None:
    """The user is told what landed in one line, without reading their Agent's config."""
    from grayom_agent_guidance.models import InstalledComponent

    installed = InstalledComponent(
        agent=AgentType.CLAUDE_CODE, component_id="example-lab", name="lab",
        type=ComponentType.PLUGIN, changed=True,
        installed_plugins=["sast@grayom-lab"], added_marketplaces=["grayom-lab"],
    )
    assert installed.summary() == (
        "Plugin sast@grayom-lab installed, marketplace grayom-lab added"
    )

    preserved = InstalledComponent(
        agent=AgentType.CLAUDE_CODE, component_id="example-lab", name="lab",
        type=ComponentType.PLUGIN,
    )
    assert preserved.summary() == "Plugin already installed"
