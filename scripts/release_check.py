"""Fast, network-free release metadata and import check."""

import importlib
import sys
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = importlib.import_module("grayom_agent_guidance")
    checks = {
        "dynamic version": "version" in project["project"]["dynamic"],
        "RC version": "rc" in package.__version__,
        "CLI import": callable(importlib.import_module("grayom_agent_guidance.cli.main").app),
        "adapter imports": all(
            hasattr(importlib.import_module("grayom_agent_guidance.adapters"), name)
            for name in ("CodexAdapter", "ClaudeCodeAdapter")
        ),
        "registry parse": bool(importlib.import_module("grayom_agent_guidance.registry").load_registry()),
        "state schema": importlib.import_module("grayom_agent_guidance.state").StateDocument().schema_version == 1,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
