"""What `grayom --help` and the menu offer, held in place.

The help output and the menu are the whole interface for someone who has just installed this.
Two things regressed before these tests existed: internal flags (`--probe-mcp`) appeared in
help as though a user should have an opinion about them, and `uninstall` existed only as a
typed command, so the menu could install but not undo.
"""

import re

from typer.testing import CliRunner

from grayom_agent_guidance.cli.main import EVERYDAY, TROUBLE, app


runner = CliRunner()

# Written out rather than read from the app, because the point is to notice when a command
# changes panel or a new one appears without anyone deciding which list it belongs in.
EVERYDAY_COMMANDS = {"setup", "recommend", "update"}
TROUBLE_COMMANDS = {"doctor", "rollback", "uninstall", "debug-info"}

MENU_ACTIONS = {"setup", "recommend", "update", "doctor", "uninstall", "rollback", "exit"}


def _help() -> str:
    result = runner.invoke(app, ["--help"], env={"COLUMNS": "100"})
    assert result.exit_code == 0
    return result.stdout


def test_every_command_is_in_one_of_the_two_panels():
    text = _help()
    everyday, trouble = text.index(EVERYDAY), text.index(TROUBLE)
    assert everyday < trouble, "the everyday commands belong above the troubleshooting ones"
    for command in EVERYDAY_COMMANDS:
        assert everyday < text.index(command) < trouble, f"{command} is not in {EVERYDAY}"
    for command in TROUBLE_COMMANDS:
        assert text.index(command) > trouble, f"{command} is not in {TROUBLE}"


def test_help_lists_no_command_beyond_the_two_panels():
    """A new command has to be placed deliberately, not appear in an unnamed third panel."""
    text = _help()
    listed = set(re.findall(r"^│ ([a-z][a-z-]+)\s{2,}", text, flags=re.M))
    assert listed == EVERYDAY_COMMANDS | TROUBLE_COMMANDS


def test_internal_flags_are_not_offered_to_users():
    text = _help() + runner.invoke(app, ["setup", "--help"], env={"COLUMNS": "100"}).stdout
    assert "--probe-mcp" not in text
    assert "--dry-run" not in text, "setup --dry-run duplicates 'grayom recommend'"


def test_hidden_flags_still_work_for_scripts_and_tests():
    """Hidden is about the help output, not about removing a flag the test suite drives."""
    result = runner.invoke(app, ["setup", "--dry-run", "--no-probe-mcp", "--offline"])
    # No TTY under CliRunner, so the interview refuses; the flags being accepted is the point,
    # and an unknown flag would exit 2 with "No such option" instead.
    assert "No such option" not in result.stdout


def test_help_text_names_no_internal_concept():
    """The words a user is not expected to know, which the first help output used throughout."""
    text = _help()
    for word in ("Reconcile", "transactionally", "sanitized", "Local Registry", "manifest"):
        assert word not in text, f"help still says {word!r}"


def test_every_command_is_reachable_from_the_menu(monkeypatch):
    """The menu is a complete way to use GrayOM, not a shortcut to part of it."""
    import grayom_agent_guidance.cli.main as main

    choices: list[dict] = []

    class Select:
        def __init__(self, **kwargs):
            choices.extend(kwargs["choices"])

        def execute(self):
            return "exit"

    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(main.inquirer, "select", Select)
    monkeypatch.setattr(main, "detect_agents", lambda: [])
    main._interactive_menu()

    assert {item["value"] for item in choices} == MENU_ACTIONS
    # Everything typed as a command is offered in the menu too, apart from debug-info, which
    # only makes sense when someone is already filing a bug report and following its text.
    assert MENU_ACTIONS - {"exit"} == (EVERYDAY_COMMANDS | TROUBLE_COMMANDS) - {"debug-info"}


def test_menu_entries_say_what_will_happen(monkeypatch):
    import grayom_agent_guidance.cli.main as main

    captured: list[str] = []

    class Select:
        def __init__(self, **kwargs):
            captured.extend(item["name"] for item in kwargs["choices"])

        def execute(self):
            return "exit"

    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(main.inquirer, "select", Select)
    monkeypatch.setattr(main, "detect_agents", lambda: [])
    main._interactive_menu()

    for name in captured:
        if name == "Exit":
            continue
        assert "  -  " in name, f"{name!r} does not say what choosing it does"
