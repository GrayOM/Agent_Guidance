from enum import StrEnum

from pydantic import BaseModel

from .agent import AgentType


class ReconciliationStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    ADD = "ADD"
    UPDATE = "UPDATE"
    REFERENCE = "REFERENCE"
    SKIP = "SKIP"
    CONFLICT = "CONFLICT"


class ReconciliationItem(BaseModel):
    agent: AgentType
    component_id: str
    status: ReconciliationStatus
    reason: str
