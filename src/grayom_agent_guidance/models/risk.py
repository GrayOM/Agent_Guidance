from enum import StrEnum

from pydantic import BaseModel


class RiskLevel(StrEnum):
    LOW = "LOW"
    WARNING = "WARNING"


class SecurityFinding(BaseModel):
    component_id: str
    level: RiskLevel
    rule: str
    message: str


class ConflictFinding(BaseModel):
    left_id: str
    right_id: str
    kind: str
    message: str

