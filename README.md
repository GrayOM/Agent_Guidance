# GrayOM Agent Guidance

AI Agent 환경에 필요한 Skill, MCP, Plugin을 추천하고 설치 계획을 검증하는 CLI 도구입니다.

현재 MVP는 Codex 감지, 선택형 업무 인터뷰, 로컬 Registry 기반 추천, 충돌·보안 분석,
Skill 설치, MCP 설정 병합, Health Check, manifest 기반 Rollback을 제공합니다. Claude Code와
Cursor 실제 설치 및 실시간 후보 탐색은 후속 단계에서 추가합니다.

## 개발 실행

```bash
python -m pip install -e '.[dev]'
grayom setup
pytest
```

`grayom`만 실행해도 `setup` 흐름이 시작됩니다. 추천만 확인하려면 `grayom recommend`, 설치 상태는
`grayom doctor`, 최근 설치 복원은 `grayom rollback`을 사용합니다.

공식 GitHub MCP를 추천받아 설치하는 경우 토큰 자체는 설정 파일에 저장하지 않습니다.

```bash
export GITHUB_PAT_TOKEN="your-token"
grayom setup
```

Skill은 `$HOME/.agents/skills`, MCP 설정은 `$HOME/.codex/config.toml`, GrayOM 백업과 설치 manifest는
`$HOME/.grayom-agent-guidance/backups`에 저장됩니다.

승인 전에는 Agent 설정을 수정하지 않습니다. `WARNING`은 설치 차단 사유가 아니며 최종 판단은
사용자에게 표시되는 일괄 설치 Plan에 포함됩니다.
