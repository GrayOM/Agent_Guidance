"""A domain or task must not reach the interview without a written label.

The interview is the only screen a user interacts with, and before these labels existed it
offered "Osint Recon" and "Ci Cd Pipeline" because the label was derived from the identifier.
A new task added to cli/interview.py's TASKS fails here until someone writes its label.
"""

import re

from agent_guidance.cli.interview import TASKS
from agent_guidance.labels import DOMAIN_LABELS, TASK_LABELS, domain_label, task_label
from agent_guidance.models import WorkDomain


def _offered_tasks() -> set[str]:
    return {task for tasks in TASKS.values() for task in tasks}


def test_every_domain_has_a_label():
    assert set(DOMAIN_LABELS) == set(WorkDomain)


def test_every_offered_task_has_a_label():
    assert _offered_tasks() - set(TASK_LABELS) == set()


def test_no_label_is_written_for_a_task_that_is_not_offered():
    """An unused label is a task that was renamed or removed and left a stale entry behind."""
    assert set(TASK_LABELS) - _offered_tasks() == set()


def test_labels_are_not_identifiers():
    """A label equal to its identifier means someone pasted the key instead of writing a label."""
    for task, label in TASK_LABELS.items():
        assert label != task
        assert "_" not in label, f"{task} label still reads as an identifier: {label}"
    for domain, label in DOMAIN_LABELS.items():
        assert "_" not in label, f"{domain.value} label still reads as an identifier: {label}"


def test_acronyms_keep_their_capitalisation():
    """The specific defect these labels fixed: .title() lowercases every acronym it meets."""
    assert task_label("osint_recon").startswith("OSINT")
    assert "CI/CD" in task_label("ci_cd_pipeline")
    assert task_label("ios_app").startswith("iOS")
    assert "LLM" in task_label("ai_llm_security")
    assert "SQL" in task_label("sql_and_database")
    assert "MCP" in task_label("mcp_based_agent")
    assert "RAG" in task_label("rag_agent")
    assert "API" in task_label("api_security_testing")
    assert domain_label(WorkDomain.OSINT) == "OSINT"
    assert domain_label(WorkDomain.DEVOPS) == "DevOps"
    assert "AI Agent" in domain_label(WorkDomain.AI_AGENT_DEVELOPMENT)


def test_labels_read_as_a_sentence_fragment():
    """Mid-label capitals are allowed only for acronyms and product names, not Title Case."""
    # Split below is on space, hyphen and slash, so "CI/CD" arrives as two words.
    allowed = re.compile(
        r"^(AI|API|APK|CD|CI|CVE|LLM|MCP|OSINT|PoC|RAG|SQL|Agent|Agents?|Android|Claude|Code|"
        r"Codex|DevOps|Kubernetes|iOS)$"
    )
    for label in [*DOMAIN_LABELS.values(), *TASK_LABELS.values()]:
        for word in re.split(r"[ \-/]", label)[1:]:
            if word and word[0].isupper() or (word and not word[0].isalpha()):
                assert allowed.match(word), f"{label!r}: unexpected capitalised word {word!r}"


def test_task_label_falls_back_for_an_identifier_from_an_older_state_file():
    assert task_label("some_removed_task") == "Some removed task"
