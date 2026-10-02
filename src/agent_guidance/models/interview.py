from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from .agent import AgentType


class SetupMode(StrEnum):
    MINIMAL = "minimal"
    PERFORMANCE = "performance"


class WorkDomain(StrEnum):
    GENERAL_DEVELOPMENT = "general_development"
    WEB_DEVELOPMENT = "web_development"
    MOBILE_DEVELOPMENT = "mobile_development"
    AI_AGENT_DEVELOPMENT = "ai_agent_development"
    SECURITY_TOOL_DEVELOPMENT = "security_tool_development"
    VULNERABILITY_RESEARCH = "vulnerability_research"
    PENETRATION_TESTING = "penetration_testing"
    OSINT = "osint"
    DEVOPS = "devops"
    DATA_ANALYSIS = "data_analysis"
    RESEARCH_WRITING = "research_writing"


class InterviewAnswer(BaseModel):
    agents: list[AgentType]
    domains: list[WorkDomain]
    tasks: list[str] = Field(default_factory=list)
    mode: SetupMode

    @model_validator(mode="after")
    def require_choices(self) -> "InterviewAnswer":
        if not self.agents:
            raise ValueError("at least one Agent must be selected")
        if not self.domains:
            raise ValueError("at least one work domain must be selected")
        return self

