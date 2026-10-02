from agent_guidance.errors import ConfigurationError, AgentGuidanceError


def test_error_model_contains_user_and_recovery_information() -> None:
    error = ConfigurationError(
        "Could not parse config", technical_message="invalid TOML at line 2",
        suggested_action="Run: agent-guidance doctor",
    )
    assert isinstance(error, AgentGuidanceError)
    assert error.recoverable
    assert "doctor" in error.suggested_action
