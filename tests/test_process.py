"""Reading a version number out of each Agent's own `--version` output."""

from agent_guidance.runtime import read_version


def test_read_version_takes_the_number_out_of_each_agents_own_format():
    """The two real formats, which were previously stored and printed raw.

    'Claude Code (2.1.287 (Claude Code))' is what the detected-Agents line used to read.
    """
    assert read_version("codex-cli 0.160.0") == "0.160.0"
    assert read_version("2.1.287 (Claude Code)") == "2.1.287"
    assert read_version("  1.2.3\n") == "1.2.3"
    assert read_version("1.0.0-beta.2") == "1.0.0-beta.2"


def test_read_version_keeps_an_unparsed_line_rather_than_dropping_it():
    assert read_version("installed from source") == "installed from source"
    assert read_version("   \n") is None
    assert read_version("") is None
