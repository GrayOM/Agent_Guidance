from grayom_agent_guidance.models import RollbackResult


def test_partial_rollback_failure_is_reported() -> None:
    result = RollbackResult(errors=["claude_code: permission denied"])
    assert not result.successful
    assert "permission denied" in result.errors[0]
