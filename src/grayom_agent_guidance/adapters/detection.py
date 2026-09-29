import shutil
from pathlib import Path

from grayom_agent_guidance.models import AgentInstallation, AgentType

from .codex import CodexAdapter


def detect_agents(home: Path | None = None) -> list[AgentInstallation]:
    root = home or Path.home()
    codex = CodexAdapter(root).detect()
    definitions = [
        (AgentType.CLAUDE_CODE, "claude", root / ".claude"),
        (AgentType.CURSOR, "cursor", root / ".cursor"),
    ]
    detected = [codex]
    for agent, command, config_root in definitions:
        executable = shutil.which(command)
        detected.append(AgentInstallation(
            agent=agent, detected=bool(executable or config_root.exists()),
            executable=Path(executable) if executable else None,
            config_path=config_root if config_root.exists() else None,
            details={"adapter_status": "planned"},
        ))
    return detected
