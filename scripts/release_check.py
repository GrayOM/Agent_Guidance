"""Fast, network-free release metadata and import check."""

import importlib
import re
import sys
import tomllib
from pathlib import Path


def _documented(version: str, changelog: str) -> bool:
    """A heading for exactly this version, not one it happens to prefix.

    A substring test passed `0.1.0` against the existing `## 0.1.0rc1` heading, which is the
    sort of false green a release gate exists to prevent.
    """
    return re.search(rf"^##\s+{re.escape(version)}(\s|$)", changelog, flags=re.M) is not None


def _is_release(version: str) -> bool:
    """A version fit to publish: PEP 440 parseable, and neither a dev nor a local build."""
    try:
        from packaging.version import Version
    except ImportError:  # packaging is a build dependency, not a runtime one
        return bool(version) and "dev" not in version and "+" not in version
    try:
        parsed = Version(version)
    except Exception:
        return False
    return not parsed.is_devrelease and parsed.local is None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = importlib.import_module("agent_guidance")
    version = package.__version__
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    checks = {
        "dynamic version": "version" in project["project"]["dynamic"],
        # "is this an RC" was the gate during the RC period and would now hold the release
        # back for being one. What matters for any version is that it parses, that it is not
        # a local or dev build, and that the changelog actually documents it: a release whose
        # notes say "Unreleased" tells a user nothing about what they installed.
        "released version": _is_release(version),
        "changelog documents this version": _documented(version, changelog),
        "CLI import": callable(importlib.import_module("agent_guidance.cli.main").app),
        "adapter imports": all(
            hasattr(importlib.import_module("agent_guidance.adapters"), name)
            for name in ("CodexAdapter", "ClaudeCodeAdapter")
        ),
        "registry parse": bool(importlib.import_module("agent_guidance.registry").load_registry()),
        "state schema": importlib.import_module("agent_guidance.state").StateDocument().schema_version == 1,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
