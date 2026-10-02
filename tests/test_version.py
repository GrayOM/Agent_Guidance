import tomllib
from pathlib import Path

from agent_guidance import __version__


def test_pyproject_uses_runtime_version_as_single_source() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["hatch"]["version"]["path"].endswith("__init__.py")
    assert __version__ == "0.1.0"
