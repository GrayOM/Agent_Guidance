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
        method = component.install_method
        if method.from_readme:
            # The approval screen said nothing about this before, so a launch command lifted
            # out of a stranger's README read exactly like one declared by a manifest. It is
            # the one thing a reader cannot recover from the component's name.
            findings.append(SecurityFinding(
                component_id=component.id, level=RiskLevel.WARNING,
                rule="install.readme_derived",
                message=(
                    "launch command was read from the repository README, which is the "
                    "repository owner's own text rather than a verified manifest"
                ),
            ))
        if method.package and method.package_version:
            findings.append(SecurityFinding(
                component_id=component.id, level=RiskLevel.LOW,
                rule="install.version_pinned",
                message=(
                    f"pinned to {method.package}@{method.package_version}, so a later "
                    "publish of this package does not change what runs"
                ),
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
