from pathlib import Path

import yaml

from grayom_agent_guidance.models import Component


REGISTRY_ROOT = Path(__file__).parent


def load_registry(root: Path = REGISTRY_ROOT) -> list[Component]:
    components: list[Component] = []
    for name in ("known_skills.yaml", "known_mcps.yaml", "known_plugins.yaml"):
        path = root / name
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        components.extend(Component.model_validate(item) for item in data)
    return components

