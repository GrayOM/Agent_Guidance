from pathlib import Path


class PathSecurityError(RuntimeError):
    pass


def validate_managed_path(path: Path, allowed_root: Path, *, allow_missing: bool = True) -> Path:
    """Reject escapes and symlinked parents before a managed write or deletion."""
    root_input = allowed_root.expanduser()
    if root_input.exists() and root_input.is_symlink():
        raise PathSecurityError(f"managed root must not be a symlink: {root_input}")
    root = root_input.resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        raise PathSecurityError(f"managed path must be absolute: {candidate}")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise PathSecurityError(f"path escapes managed root {root}: {candidate}")
    current = candidate
    while current != root and current != current.parent:
        if current.exists() and current.is_symlink():
            raise PathSecurityError(f"symlink is not allowed in managed path: {current}")
        current = current.parent
    if not allow_missing and not candidate.exists():
        raise PathSecurityError(f"managed path does not exist: {candidate}")
    return resolved
