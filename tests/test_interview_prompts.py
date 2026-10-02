"""Cover the interview, the one user-facing path nothing had executed.

`run_interview` builds the InquirerPy prompts a user actually answers, and had 30% coverage:
every other test, and every end-to-end run, called `build_answer` with a scripted answer
instead. So which Agents are offered, which domains, the detailed questions per domain and
the mode had no automated verification that they render at all, let alone return what was
picked.

It is covered in two halves, because one pre-filled pipe cannot drive the whole interview:
prompt_toolkit's first Application reads everything buffered and drops what it does not
consume, so prompt two starves — it hangs with the pipe open and raises EOFError with it
closed. Measured both ways before settling on this split.

- the prompts themselves run for real, one per test, against the choice structures
  `run_interview` builds
- the interview's own logic runs for real against a recorder in place of the prompts, so the
  order of the questions, the choices handed to each one and both refusals are asserted
"""

import sys
from typing import Any

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from InquirerPy import inquirer

import grayom_agent_guidance.cli.interview as interview
from grayom_agent_guidance.cli.interview import DOMAIN_LABELS, TASKS, run_interview
from grayom_agent_guidance.labels import domain_label
from grayom_agent_guidance.models import AgentInstallation, AgentType, SetupMode, WorkDomain


ENTER = "\r"
SPACE = " "
DOWN = "\x1b[B"


def installed(*agents: AgentType) -> list[AgentInstallation]:
    return [
        AgentInstallation(agent=agent, detected=agent in agents)
        for agent in (AgentType.CODEX, AgentType.CLAUDE_CODE)
    ]


@pytest.fixture(autouse=True)
def pretend_a_terminal(monkeypatch):
    """The interview refuses to run without a TTY, and a pipe is not one."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)


def driven(keys: str, build):
    """Run one real prompt against a scripted keystroke sequence.

    The pipe is closed after the keys, so a prompt reading past the end raises EOFError
    rather than waiting forever: a wrong sequence fails in milliseconds instead of hanging
    the suite, which is what happened the first time these were written.
    """
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        pipe.close()
        with create_app_session(input=pipe, output=DummyOutput()):
            return build().execute()


# --- the prompts a user sees ---------------------------------------------------------


def test_a_detected_agent_comes_pre_selected_so_enter_accepts_it() -> None:
    """`run_interview` marks a detected Agent `enabled`, which has to mean selected."""
    result = driven(ENTER, lambda: inquirer.checkbox(
        message="Select AI Agents:",
        choices=[{"name": "Claude Code", "value": AgentType.CLAUDE_CODE, "enabled": True}],
        validate=lambda value: bool(value), invalid_message="Select at least one Agent",
    ))

    assert result == [AgentType.CLAUDE_CODE]


def test_a_checkbox_returns_the_entry_the_user_moved_to_and_toggled() -> None:
    """Six downs and a space must select the seventh domain, not the first."""
    choices = [{"name": label, "value": value} for label, value in DOMAIN_LABELS.items()]
    target = WorkDomain.PENETRATION_TESTING
    steps = list(DOMAIN_LABELS.values()).index(target)

    result = driven(DOWN * steps + SPACE + ENTER, lambda: inquirer.checkbox(
        message="Select Work Domains:", choices=choices,
        validate=lambda value: bool(value), invalid_message="Select at least one domain",
    ))

    assert result == [target]


def test_an_empty_checkbox_answer_is_rejected_and_the_prompt_waits() -> None:
    """An empty domain answer would infer no capability and recommend nothing.

    The prompt must not accept it; pressing Enter with nothing toggled leaves it open, which
    here exhausts the scripted input and raises rather than returning [].
    """
    choices = [{"name": label, "value": value} for label, value in DOMAIN_LABELS.items()]

    with pytest.raises(EOFError):
        driven(ENTER, lambda: inquirer.checkbox(
            message="Select Work Domains:", choices=choices,
            validate=lambda value: bool(value), invalid_message="Select at least one domain",
        ))


def test_the_mode_prompt_returns_the_second_choice_when_moved_to_it() -> None:
    build = lambda: inquirer.select(  # noqa: E731 - one expression, read as data
        message="Configuration mode:",
        choices=[{"name": "Minimal", "value": SetupMode.MINIMAL},
                 {"name": "Performance", "value": SetupMode.PERFORMANCE}],
    )

    assert driven(ENTER, build) == SetupMode.MINIMAL
    assert driven(DOWN + ENTER, build) == SetupMode.PERFORMANCE


# --- the interview's own logic -------------------------------------------------------


class Recorder:
    """Stands in for the prompts so the real interview logic runs and can be inspected."""

    def __init__(self, answers: list[Any]) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, str, list[Any]]] = []

    def _prompt(self, kind: str, **kwargs: Any):
        self.asked.append((
            kind, kwargs["message"],
            [choice["value"] for choice in kwargs.get("choices", [])],
        ))
        recorder = self

        class _Prompt:
            def execute(self) -> Any:
                assert recorder.answers, f"the interview asked more than expected: {kwargs['message']}"
                return recorder.answers.pop(0)

        return _Prompt()

    def checkbox(self, **kwargs: Any):
        return self._prompt("checkbox", **kwargs)

    def select(self, **kwargs: Any):
        return self._prompt("select", **kwargs)


def interviewed(monkeypatch, detected, answers):
    recorder = Recorder(answers)
    monkeypatch.setattr(interview.inquirer, "checkbox", recorder.checkbox)
    monkeypatch.setattr(interview.inquirer, "select", recorder.select)
    return run_interview(detected), recorder


def test_the_interview_asks_agents_then_domains_then_tasks_then_mode(monkeypatch) -> None:
    target = WorkDomain.PENETRATION_TESTING
    answer, recorder = interviewed(
        monkeypatch, installed(AgentType.CLAUDE_CODE),
        [[AgentType.CLAUDE_CODE], [target], [TASKS[target][0]], SetupMode.MINIMAL],
    )

    assert [kind for kind, _, _ in recorder.asked] == [
        "checkbox", "checkbox", "checkbox", "select",
    ]
    assert recorder.asked[2][1] == f"Select tasks for {domain_label(WorkDomain.PENETRATION_TESTING)}:"
    assert recorder.asked[2][2] == TASKS[target]
    assert answer.agents == [AgentType.CLAUDE_CODE]
    assert answer.domains == [target]
    assert answer.tasks == [TASKS[target][0]]
    assert answer.mode == SetupMode.MINIMAL


def test_an_agent_that_is_not_installed_is_never_offered(monkeypatch) -> None:
    """GrayOM does not install Agents, so it must not offer to configure a missing one.

    InquirerPy's checkbox has no unselectable entry, so an undetected Agent is withheld from
    the list rather than shown disabled — which is what keeps Enter from selecting it.
    """
    _, recorder = interviewed(
        monkeypatch, installed(AgentType.CODEX),
        [[AgentType.CODEX], [WorkDomain.GENERAL_DEVELOPMENT], [], SetupMode.MINIMAL],
    )

    assert recorder.asked[0][2] == [AgentType.CODEX]


def test_both_detected_agents_are_offered_when_both_are_present(monkeypatch) -> None:
    _, recorder = interviewed(
        monkeypatch, installed(AgentType.CODEX, AgentType.CLAUDE_CODE),
        [[AgentType.CODEX, AgentType.CLAUDE_CODE], [WorkDomain.GENERAL_DEVELOPMENT], [],
         SetupMode.MINIMAL],
    )

    assert recorder.asked[0][2] == [AgentType.CODEX, AgentType.CLAUDE_CODE]


def test_every_agent_is_offered_when_detection_was_not_run(monkeypatch) -> None:
    """`grayom recommend` may ask before detecting, and then nothing is withheld."""
    _, recorder = interviewed(
        monkeypatch, None,
        [[AgentType.CODEX], [WorkDomain.GENERAL_DEVELOPMENT], [], SetupMode.MINIMAL],
    )

    assert recorder.asked[0][2] == [AgentType.CODEX, AgentType.CLAUDE_CODE]


def test_two_domains_each_get_their_own_detailed_question(monkeypatch) -> None:
    """The detailed questions are per domain; one prompt for both would discard half.

    The selected tasks are what makes one profile differ from another, so each domain has to
    be asked with its own list.
    """
    first, second = WorkDomain.GENERAL_DEVELOPMENT, WorkDomain.PENETRATION_TESTING
    answer, recorder = interviewed(
        monkeypatch, installed(AgentType.CLAUDE_CODE),
        [[AgentType.CLAUDE_CODE], [first, second],
         [TASKS[first][0]], [TASKS[second][0]], SetupMode.PERFORMANCE],
    )

    task_prompts = [item for item in recorder.asked if item[1].startswith("Select tasks")]
    assert [item[2] for item in task_prompts] == [TASKS[first], TASKS[second]]
    assert answer.tasks == [TASKS[first][0], TASKS[second][0]]
    assert answer.mode == SetupMode.PERFORMANCE


def test_the_interview_refuses_to_run_without_a_terminal(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    with pytest.raises(RuntimeError, match="TTY"):
        run_interview(installed(AgentType.CLAUDE_CODE))


def test_no_detected_agent_is_a_refusal_not_an_empty_setup(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="does not install Agents"):
        interviewed(monkeypatch, installed(), [])
