from agent_guidance.models import Ownership


def test_ownership_states_are_explicit() -> None:
    assert set(Ownership) == {
        Ownership.EXISTING, Ownership.AGENT_GUIDANCE_INSTALLED, Ownership.AGENT_GUIDANCE_MODIFIED, Ownership.SHARED,
    }
