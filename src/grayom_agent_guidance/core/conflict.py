from itertools import combinations

from grayom_agent_guidance.models import Component, ConflictFinding


def analyze_conflicts(components: list[Component]) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    for left, right in combinations(components, 2):
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
    return findings

