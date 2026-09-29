import pytest
from pydantic import ValidationError

from grayom_agent_guidance.models import InterviewAnswer, RiskLevel, SetupMode


def test_risk_levels_are_limited() -> None:
    assert set(RiskLevel) == {RiskLevel.LOW, RiskLevel.WARNING}


def test_interview_requires_agent_and_domain() -> None:
    with pytest.raises(ValidationError):
        InterviewAnswer(agents=[], domains=[], mode=SetupMode.MINIMAL)

