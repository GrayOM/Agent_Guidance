from grayom_agent_guidance.core import analyze_security
from grayom_agent_guidance.models import (
    AgentType, Compatibility, Component, ComponentType, DependencyRequirement,
    Permission, RiskLevel,
)


def test_shell_is_warning_but_network_is_low() -> None:
    target = Component(
        id="test", name="test", type=ComponentType.SKILL,
        source_url="https://github.com/example/example", compatibility=Compatibility(agents={AgentType.CODEX}),
        permissions={Permission.SHELL, Permission.NETWORK},
    )
    levels = {finding.rule: finding.level for finding in analyze_security([target])}
    assert levels["permission.shell"] == RiskLevel.WARNING
    assert levels["permission.network"] == RiskLevel.LOW


def test_missing_runtime_creates_warning_without_installing_it() -> None:
    target = Component(
        id="runtime", name="runtime", type=ComponentType.MCP,
        source_url="https://github.com/example/runtime",
        compatibility=Compatibility(agents={AgentType.CODEX}),
        dependencies=[DependencyRequirement(name="Node.js", executable="node", detected=False)],
    )
    findings = analyze_security([target])
    assert any(item.rule == "dependency.node" and item.level == RiskLevel.WARNING for item in findings)
