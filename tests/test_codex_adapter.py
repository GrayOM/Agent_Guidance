from grayom_agent_guidance.adapters import CodexAdapter


def test_backup_health_and_rollback(tmp_path) -> None:
    home = tmp_path / "home"
    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "test"\n', encoding="utf-8")
    adapter = CodexAdapter(home=home)
    assert adapter.detect().detected
    assert adapter.health_check().healthy

    manifest = adapter.backup(tmp_path / "backup")
    config.write_text("broken = [", encoding="utf-8")
    assert not adapter.health_check().healthy
    result = adapter.rollback(manifest)
    assert result.successful
    assert config.read_text(encoding="utf-8") == 'model = "test"\n'
