import re
from dataclasses import dataclass, field

from agent_guidance.models import EvidenceItem, SecurityMetadata


@dataclass
class RepositorySecurityResult:
    metadata: SecurityMetadata = field(default_factory=SecurityMetadata)
    evidence: list[EvidenceItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "shell_execution": [re.compile(r"\b(?:bash|sh|zsh)\s+-c\b"), re.compile(r"shell\s*=\s*True")],
    "subprocess": [re.compile(r"\bsubprocess\.(?:run|Popen|call)\s*\("), re.compile(r"child_process")],
    "external_download": [re.compile(r"\bcurl\b.+https?://"), re.compile(r"\bwget\b.+https?://")],
    "network_access": [re.compile(r"https?://"), re.compile(r"\brequests\.(?:get|post)\s*\(")],
    "filesystem_delete": [re.compile(r"\brm\s+-rf\b"), re.compile(r"shutil\.rmtree\s*\(")],
    "credential_access": [re.compile(r"(?:\.env|id_rsa|GITHUB_TOKEN|API_KEY|credential)", re.I)],
    "destructive_operations": [re.compile(r"\bgit\s+reset\s+--hard\b"), re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I)],
    "install_script": [re.compile(r"(?:install|postinstall|preinstall)\s*[\"']?\s*:")],
    "update_script": [re.compile(r"(?:self[-_ ]?update|update\.sh|upgrade\.sh)", re.I)],
}


def scan_repository(files: dict[str, str]) -> RepositorySecurityResult:
    result = RepositorySecurityResult()
    matches: dict[str, list[tuple[str, str]]] = {key: [] for key in PATTERNS}
    for path, content in files.items():
        sample = content[:250_000]
        for finding_field, patterns in PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(sample)
                if match:
                    matches[finding_field].append((path, match.group(0)[:120]))
                    break

    for finding_field, found in matches.items():
        if not found:
            continue
        # Generic URLs alone are LOW evidence; dangerous execution and deletion patterns are high-confidence.
        setattr(result.metadata, finding_field, True)
        for path, excerpt in found[:3]:
            result.evidence.append(EvidenceItem(
                field=f"security.{finding_field}", value=True, source="repository_file",
                location=f"{path}: {excerpt}",
            ))
        if finding_field != "network_access":
            result.warnings.append(
                f"repository evidence indicates {finding_field.replace('_', ' ')}"
            )
    return result
