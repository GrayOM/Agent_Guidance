from itertools import combinations

from grayom_agent_guidance.models import Component, ConflictFinding


def analyze_conflicts(components: list[Component]) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    for left, right in combinations(components, 2):
        if left.id in right.conflicts or right.id in left.conflicts:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="explicit_conflict",
                message="registry declares these components incompatible",
            ))
        if left.type == right.type and left.type.value == "mcp" and left.capabilities == right.capabilities:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="duplicate_mcp",
                message="MCP servers provide the same capability set",
            ))
        if overlap := left.tool_names & right.tool_names:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="tool_name",
                message=f"duplicate tool names: {', '.join(sorted(overlap))}",
            ))
        if overlap := left.config_targets & right.config_targets:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="config_target",
                message=f"both modify: {', '.join(sorted(overlap))}",
            ))
        if left.id in right.included_components or right.id in left.included_components:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="bundled_duplicate",
                message="component is already included by another component",
            ))
        if overlap := left.install_paths & right.install_paths:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="install_path",
                message=f"both install to: {', '.join(sorted(overlap))}",
            ))
        if overlap := left.config_keys & right.config_keys:
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="config_key",
                message=f"both control config keys: {', '.join(sorted(overlap))}",
            ))
        if left.workflows and right.workflows and left.workflows.isdisjoint(right.workflows):
            findings.append(ConflictFinding(
                left_id=left.id, right_id=right.id, kind="workflow",
                message="components require different workflows",
            ))
    return findings
