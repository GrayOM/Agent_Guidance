from grayom_agent_guidance.models import Ownership


def test_ownership_states_are_explicit() -> None:
    assert set(Ownership) == {
        Ownership.EXISTING, Ownership.GRAYOM_INSTALLED, Ownership.GRAYOM_MODIFIED, Ownership.SHARED,
    }
