"""What `agent-guidance --help` and the menu offer, held in place.

The help output and the menu are the whole interface for someone who has just installed this.
Two things regressed before these tests existed: internal flags (`--probe-mcp`) appeared in
help as though a user should have an opinion about them, and `uninstall` existed only as a
typed command, so the menu could install but not undo.
"""

from typer.testing import CliRunner

from agent_guidance.cli.main import EVERYDAY, TROUBLE, app


runner = CliRunner()

# Written out rather than read from the app, because the point is to notice when a command
# changes panel or a new one appears without anyone deciding which list it belongs in.
EVERYDAY_COMMANDS = {"setup", "recommend", "update"}
TROUBLE_COMMANDS = {"doctor", "rollback", "uninstall", "debug-info", "self-check"}

MENU_ACTIONS = {"setup", "recommend", "update", "doctor", "uninstall", "rollback", "exit"}


def _help() -> str:
    result = runner.invoke(app, ["--help"], env={"COLUMNS": "100"})
    assert result.exit_code == 0
    return result.stdout


def _panels() -> dict[str, str | None]:
    """Each command's panel, read from the app rather than from its rendered help.

    An earlier version of this file pulled the command names out of the help text with a
    regex anchored on Rich's box-drawing border. It passed here and found nothing in CI,
    where Rich draws the same panels with a different character set. What the test is
    actually about -- that every command is deliberately placed in one of two panels -- is
    recorded on the app itself, so that is what it reads.
    """
    return {
        command.name or command.callback.__name__.replace("_", "-"): command.rich_help_panel
        for command in app.registered_commands
    }


def test_every_command_is_in_one_of_the_two_panels():
    panels = _panels()
    assert {name for name, panel in panels.items() if panel == EVERYDAY} == EVERYDAY_COMMANDS
    assert {name for name, panel in panels.items() if panel == TROUBLE} == TROUBLE_COMMANDS


def test_no_command_sits_outside_the_two_panels():
    """A new command has to be placed deliberately, not land in an unnamed third panel."""
    assert set(_panels()) == EVERYDAY_COMMANDS | TROUBLE_COMMANDS
    assert all(panel in {EVERYDAY, TROUBLE} for panel in _panels().values())


def test_the_help_shows_the_everyday_commands_first():
    text = _help()
    assert text.index(EVERYDAY) < text.index(TROUBLE)
    for command in EVERYDAY_COMMANDS | TROUBLE_COMMANDS:
        assert command in text


def test_internal_flags_are_not_offered_to_users():
    text = _help() + runner.invoke(app, ["setup", "--help"], env={"COLUMNS": "100"}).stdout
    assert "--probe-mcp" not in text
    assert "--dry-run" not in text, "setup --dry-run duplicates 'agent-guidance recommend'"


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
    """The menu is a complete way to use Agent Guidance, not a shortcut to part of it."""
    import agent_guidance.cli.main as main

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
    # Everything typed as a command is offered in the menu too, apart from two that are only
    # reached by following written instructions: debug-info, when someone is already filing a
    # bug report, and self-check, when someone is deciding whether to trust or publish this.
    # "Check my setup" is already in the menu and means something else: whether what is
    # installed still works, not whether the program does what it claims.
    assert MENU_ACTIONS - {"exit"} == (
        (EVERYDAY_COMMANDS | TROUBLE_COMMANDS) - {"debug-info", "self-check"}
    )


def test_menu_entries_say_what_will_happen(monkeypatch):
    import agent_guidance.cli.main as main

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
