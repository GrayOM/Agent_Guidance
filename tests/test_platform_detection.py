from grayom_agent_guidance.core.platform import EnvironmentType, OperatingSystem, detect_platform


def test_wsl_detection_adds_warning(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "5.15-microsoft-standard-WSL2")
    result = detect_platform(tmp_path)
    assert result.os == OperatingSystem.LINUX
    assert result.environment == EnvironmentType.WSL
    assert result.warnings
