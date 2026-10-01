import os
import platform as std_platform
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class OperatingSystem(StrEnum):
    WINDOWS = "WINDOWS"
    MACOS = "MACOS"
    LINUX = "LINUX"
    UNKNOWN = "UNKNOWN"


class EnvironmentType(StrEnum):
    NATIVE = "NATIVE"
    WSL = "WSL"


class PlatformInfo(BaseModel):
    os: OperatingSystem
    environment: EnvironmentType
    home: Path
    shell: str | None = None
    path_style: str
    warnings: list[str] = Field(default_factory=list)


def detect_platform(home: Path | None = None) -> PlatformInfo:
    system = std_platform.system().lower()
    os_type = {
        "windows": OperatingSystem.WINDOWS,
        "darwin": OperatingSystem.MACOS,
        "linux": OperatingSystem.LINUX,
    }.get(system, OperatingSystem.UNKNOWN)
    release = std_platform.release().lower()
    proc_version = ""
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        pass
    is_wsl = os_type == OperatingSystem.LINUX and (
        "microsoft" in release or "microsoft" in proc_version or bool(os.environ.get("WSL_DISTRO_NAME"))
    )
    warnings = []
    if is_wsl:
        warnings.append(
            "WSL detected; a Windows-hosted Agent's configuration is not modified automatically"
        )
    if os_type == OperatingSystem.UNKNOWN:
        warnings.append("unsupported platform; only explicit user-home paths are considered")
    return PlatformInfo(
        os=os_type, environment=EnvironmentType.WSL if is_wsl else EnvironmentType.NATIVE,
        home=(home or Path.home()).resolve(), shell=os.environ.get("SHELL") or os.environ.get("COMSPEC"),  # nosec
        path_style="windows" if os_type == OperatingSystem.WINDOWS else "posix", warnings=warnings,
    )
