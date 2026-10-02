from agent_guidance.adapters import AgentAdapter


def test_adapter_contract_includes_inspection_version_and_inventory() -> None:
    expected = {
        "capabilities", "detect", "inspect", "get_version", "get_config_paths", "backup",
        "list_existing_skills", "list_existing_mcps", "list_existing_plugins",
        "install_skill", "configure_mcp", "install_plugin", "health_check", "rollback",
    }
    assert expected <= set(AgentAdapter.__abstractmethods__)
