from grayom_agent_guidance.models import Component, Permission, RiskLevel, SecurityFinding


WARNING_PERMISSIONS = {
    Permission.FILESYSTEM_WRITE, Permission.SHELL, Permission.SUBPROCESS,
    Permission.CREDENTIALS, Permission.REPOSITORY_WRITE, Permission.DESTRUCTIVE,
}


def analyze_security(components: list[Component]) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for component in components:
        for permission in sorted(component.permissions, key=lambda value: value.value):
            warning = permission in WARNING_PERMISSIONS
            findings.append(SecurityFinding(
                component_id=component.id,
                level=RiskLevel.WARNING if warning else RiskLevel.LOW,
                rule=f"permission.{permission.value}",
                message=f"requests {permission.value.replace('_', ' ')} access",
            ))
        if component.install_command:
            findings.append(SecurityFinding(
                component_id=component.id, level=RiskLevel.WARNING,
                rule="install.external_command", message="installation executes an external command",
            ))
    return findings

