from pathlib import Path

from agent_guidance.models import AgentInstallation

from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter


def detect_agents(home: Path | None = None) -> list[AgentInstallation]:
    root = home or Path.home()
    return [CodexAdapter(root).detect(), ClaudeCodeAdapter(root).detect()]
