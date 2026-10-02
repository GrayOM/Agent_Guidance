from agent_guidance.observability import EventLogger, redact


def test_secret_values_are_redacted_from_logs(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    EventLogger(path).write(
        "failure", api_token="secret-value", message="Authorization: Bearer abc.def",
    )
    text = path.read_text(encoding="utf-8")
    assert "secret-value" not in text and "abc.def" not in text
    assert "REDACTED" in text
    assert redact({"password": "x"}) == {"password": "[REDACTED]"}
