from grayom_agent_guidance.core.shared_components import SharedComponentManager
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, SharedComponentRecord, Ownership,
)


def test_shared_mcp_is_prepared_only_once() -> None:
    component = Component(
        id="shared", name="Shared", type=ComponentType.MCP,
        github_url="https://github.com/example/shared",
        supported_agents={AgentType.CODEX, AgentType.CLAUDE_CODE},
        capabilities={Capability.REPOSITORY_ACCESS},
    )
    record = SharedComponentRecord(
        component_id="shared", ownership=Ownership.SHARED, shared=True,
        used_by=[AgentType.CODEX, AgentType.CLAUDE_CODE],
    )
    manager = SharedComponentManager()
    manager.prepare(component, record)
    manager.prepare(component, record)
    assert manager.prepared == {"shared"}
    assert record.prepared_count == 1
