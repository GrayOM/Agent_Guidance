from dataclasses import dataclass, field

from grayom_agent_guidance.models import Component


@dataclass
class CandidateCache:
    items: dict[str, Component] = field(default_factory=dict)

