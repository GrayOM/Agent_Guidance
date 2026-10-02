from agent_guidance.models import Component, Permission, RiskLevel, SecurityFinding


WARNING_PERMISSIONS = {
    Permission.FILESYSTEM_WRITE, Permission.SHELL, Permission.SUBPROCESS,
    Permission.CREDENTIALS, Permission.REPOSITORY_WRITE, Permission.DESTRUCTIVE,
    Permission.EXTERNAL_DOWNLOAD, Permission.FILESYSTEM_DELETE,
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
        executable = component.install_method.command
        if executable and executable.lower() in {"sudo", "su", "doas", "runas"}:
            findings.append(SecurityFinding(
                component_id=component.id, level=RiskLevel.WARNING,
                rule="install.privileged",
                message="requires a privileged installation step; Agent Guidance will not elevate privileges",
            ))
        metadata = component.security_metadata
        permission_equivalents = {
            "shell_execution": Permission.SHELL,
            "subprocess": Permission.SUBPROCESS,
            "external_download": Permission.EXTERNAL_DOWNLOAD,
            "network_access": Permission.NETWORK,
            "filesystem_write": Permission.FILESYSTEM_WRITE,
            "filesystem_delete": Permission.FILESYSTEM_DELETE,
            "credential_access": Permission.CREDENTIALS,
            "repository_write": Permission.REPOSITORY_WRITE,
            "destructive_operations": Permission.DESTRUCTIVE,
        }
        for field in (
            "shell_execution", "subprocess", "external_download", "network_access",
            "filesystem_write", "filesystem_delete", "credential_access", "repository_write",
            "destructive_operations", "install_script", "update_script",
        ):
            if getattr(metadata, field) and permission_equivalents.get(field) not in component.permissions:
                findings.append(SecurityFinding(
                    component_id=component.id,
                    level=RiskLevel.LOW if field == "network_access" else RiskLevel.WARNING,
                    rule=f"security.{field}", message=field.replace("_", " "),
                ))
        for dependency in component.dependencies:
            if dependency.required and dependency.detected is False:
                findings.append(SecurityFinding(
                    component_id=component.id, level=RiskLevel.WARNING,
                    rule=f"dependency.{dependency.executable}",
                    message=f"{dependency.name} is required but was not detected",
                ))
        for warning in component.validation_warnings:
            findings.append(SecurityFinding(
                component_id=component.id, level=RiskLevel.WARNING,
                rule="candidate.validation", message=warning,
            ))
    return findings
