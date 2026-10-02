import json

from agent_guidance.adapters import CodexAdapter
from agent_guidance.core import InstallationTransaction
from agent_guidance.models import (
    AgentType, CheckResult, Component, ComponentInstallResult, ComponentType,
    HealthCheckResult, InstallationManifest,
)


def test_rollback_restores_config_and_removes_only_created_components(tmp_path) -> None:
    home = tmp_path / "home"
    adapter = CodexAdapter(home=home)
    adapter.codex_home.mkdir(parents=True)
    adapter.config_path.write_text('model = "original"\n', encoding="utf-8")
    backup = adapter.backup(tmp_path / "backup")
    manifest = InstallationManifest(backup=backup)

    created = adapter.skills_root / "created"
    existing = adapter.skills_root / "existing"
    created.mkdir(parents=True)
    existing.mkdir(parents=True)
    created.joinpath(".agent-guidance-component.json").write_text(
        json.dumps({"component_id": "created"}), encoding="utf-8",
    )
    existing.joinpath("SKILL.md").write_text("user content", encoding="utf-8")
    manifest.created_paths.append(created)
    manifest.preserved_paths.append(existing)
    adapter.config_path.write_text('model = "changed"\n', encoding="utf-8")

    result = adapter.rollback(manifest)
    assert result.successful
    assert not created.exists()
    assert existing.exists()
    assert adapter.config_path.read_text(encoding="utf-8") == 'model = "original"\n'


def test_rollback_removes_config_that_did_not_exist_before_install(tmp_path) -> None:
    adapter = CodexAdapter(home=tmp_path / "home")
    backup = adapter.backup(tmp_path / "backup")
    manifest = InstallationManifest(backup=backup)
    adapter.config_path.parent.mkdir(parents=True)
    adapter.config_path.write_text("[mcp_servers.test]\nurl = \"https://example.com\"\n", encoding="utf-8")

    result = adapter.rollback(manifest)
    assert result.successful
    assert not adapter.config_path.exists()


def test_transaction_rolls_back_after_fatal_health_failure(tmp_path, monkeypatch) -> None:
    adapter = CodexAdapter(home=tmp_path / "home")
    adapter.codex_home.mkdir(parents=True)
    adapter.config_path.write_text('model = "original"\n', encoding="utf-8")
    component = Component(
        id="demo", name="Demo", type=ComponentType.SKILL,
        github_url="https://github.com/example/demo", supported_agents={AgentType.CODEX},
    )
    created = adapter.skills_root / "demo"

    def install(_component):
        created.mkdir(parents=True)
        created.joinpath(".agent-guidance-component.json").write_text(
            json.dumps({"component_id": "demo"}), encoding="utf-8",
        )
        return ComponentInstallResult(component_id="demo", changed=True, created_paths=[created])

    monkeypatch.setattr(adapter, "install_skill", install)
    monkeypatch.setattr(adapter, "health_check", lambda *args, **kwargs: HealthCheckResult(
        checks=[CheckResult(name="fatal", passed=False, message="failed")],
    ))
    result = InstallationTransaction(adapter, tmp_path / "backups").execute([component])

    assert not result.success
    assert result.rollback and result.rollback.successful
    assert not created.exists()
    assert adapter.config_path.read_text(encoding="utf-8") == 'model = "original"\n'
