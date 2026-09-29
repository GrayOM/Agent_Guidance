# GrayOM Agent Guidance

AI Agent 환경에 필요한 Skill, MCP, Plugin을 추천하고 설치 계획을 검증하는 CLI 도구입니다.

현재 MVP는 Codex 감지, 선택형 업무 인터뷰, 로컬 Registry 기반 추천, 충돌·보안 분석,
설정 백업 및 Health Check 골격을 제공합니다. Claude Code와 Cursor 지원 및 실시간 후보 탐색은
후속 단계에서 추가합니다.

## 개발 실행

```bash
python -m pip install -e '.[dev]'
grayom setup
pytest
```

승인 전에는 Agent 설정을 수정하지 않습니다. `WARNING`은 설치 차단 사유가 아니며 최종 판단은
사용자에게 표시되는 일괄 설치 Plan에 포함됩니다.

