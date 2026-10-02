from agent_guidance.state import ManagedComponent, StateStore
from agent_guidance.models import AgentType, Ownership


def test_state_round_trip_contains_no_profile_or_secret(tmp_path) -> None:
    path = tmp_path / "components.json"
    state = StateStore(path)
    state.document.components["demo"] = ManagedComponent(
        component_id="demo", agents=[AgentType.CODEX], ownership=Ownership.AGENT_GUIDANCE_INSTALLED,
        transaction_id="tx",
    )
    state.save()
    loaded = StateStore(path)
    assert loaded.document.components["demo"].transaction_id == "tx"
    assert "profile" not in path.read_text(encoding="utf-8").lower()
    component_manifest = path.parent / "component-manifests" / "demo.json"
    assert component_manifest.exists()
    assert '"schema_version": 1' in component_manifest.read_text(encoding="utf-8")
