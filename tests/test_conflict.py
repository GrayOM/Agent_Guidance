from grayom_agent_guidance.core import analyze_conflicts
from grayom_agent_guidance.models import AgentType, Compatibility, Component, ComponentType


def component(identifier: str) -> Component:
    return Component(
        id=identifier, name=identifier, type=ComponentType.MCP,
        source_url="https://github.com/example/example", compatibility=Compatibility(agents={AgentType.CODEX}),
        tool_names={"read_file"}, config_targets={"codex.config.toml"},
    )


def test_detects_cross_component_conflicts() -> None:
    findings = analyze_conflicts([component("one"), component("two")])
    assert {finding.kind for finding in findings} == {"tool_name", "config_target"}

