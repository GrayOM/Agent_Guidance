from grayom_agent_guidance.errors import ConfigurationError, GrayOMError


def test_error_model_contains_user_and_recovery_information() -> None:
    error = ConfigurationError(
        "Could not parse config", technical_message="invalid TOML at line 2",
        suggested_action="Run: grayom doctor",
    )
    assert isinstance(error, GrayOMError)
    assert error.recoverable
    assert "doctor" in error.suggested_action
