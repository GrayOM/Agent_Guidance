# Security Policy

## Managed scope

GrayOM Agent Guidance는 사용자가 최종 Plan을 승인한 뒤 다음 AI Agent 관련 경로만 수정합니다.

- Codex: `CODEX_HOME/config.toml` 또는 `~/.codex/config.toml`, `~/.agents/skills/`
- Claude Code: `~/.claude.json`, `~/.claude/settings.json`, `~/.claude/skills/`
- Cursor: `~/.cursor/mcp.json`, `~/.cursor/skills/`, `~/.cursor/plugins/local/`
- GrayOM 자체 데이터: `~/.grayom/` 또는 `GRAYOM_HOME`

GrayOM은 일반 IDE 설정, 개발 runtime, Docker, Git, Agent 애플리케이션을 설치하거나 수정하지 않습니다.

## External components

추천된 외부 component가 안전하다고 보증하지 않습니다. GrayOM은 repository metadata, manifest,
설치 방식과 파일 증거를 바탕으로 shell, subprocess, network, credential, filesystem write/delete,
destructive command, install/update script 신호를 분석합니다. 공개 위험 등급은 `LOW`와 `WARNING`만
사용하며 `WARNING`은 자동 차단 사유가 아닙니다.

## Credentials

Credential 값은 CLI Plan, cache, state, event log, debug bundle에 저장하지 않습니다. Agent 설정에는
가능한 경우 환경변수 참조만 기록합니다. JSONL log와 debug info는 알려진 secret key와 Bearer token을
redact합니다.

## Backup and rollback

모든 선택 Agent의 설정을 첫 변경 전에 `~/.grayom/backups/<transaction-id>/`에 백업합니다. 설치 중
치명적 Health Check가 실패하면 전체 Agent를 역순으로 rollback합니다. GrayOM marker가 없는 사용자
기존 Skill/Plugin 경로는 제거하지 않습니다. rollback 자체가 일부 실패하면 정확한 오류 목록을
manifest와 CLI에 남깁니다.

## Reporting a vulnerability

공개 Issue에 token, 설정 원문, backup, private repository URL을 첨부하지 마십시오. 재현 절차,
영향받는 GrayOM version, 운영체제, sanitized `grayom debug-info` 출력만 포함해 repository maintainer의
비공개 보안 연락 경로로 보고하십시오.
