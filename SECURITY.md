# Security Policy

## Managed scope

Agent Guidance는 사용자가 최종 Plan을 승인한 뒤 다음 AI Agent 관련 경로만 수정합니다.

- Codex: `CODEX_HOME/config.toml` 또는 `~/.codex/config.toml`, `~/.agents/skills/`
- Claude Code: `~/.claude.json`, `~/.claude/settings.json`, `~/.claude/skills/`
- Agent Guidance 자체 데이터: `~/.agent-guidance/` 또는 `AGENT_GUIDANCE_HOME`

Agent Guidance는 일반 IDE 설정, 개발 runtime, Docker, Git, Agent 애플리케이션을 설치하거나 수정하지 않습니다.

## External components

추천된 외부 component가 안전하다고 보증하지 않습니다. Agent Guidance는 repository metadata, manifest,
설치 방식과 파일 증거를 바탕으로 shell, subprocess, network, credential, filesystem write/delete,
destructive command, install/update script 신호를 분석합니다. 공개 위험 등급은 `LOW`와 `WARNING`만
사용하며 `WARNING`은 자동 차단 사유가 아닙니다.

`Official`은 provenance 신호이지 안전 보증이 아닙니다. Trust와 Security 평가는 분리되며 공식
component도 credential, network, shell 또는 repository write 권한 때문에 `WARNING`일 수 있습니다.

## Install provenance and pinning

설치되는 것은 버전을 고정합니다. Skill과 Plugin repository는 발견 시점의 commit(`head_sha`)으로,
npm으로 실행되는 MCP 서버는 npm registry가 보고한 정확한 버전으로 고정합니다. 고정되지 않은 설치는
승인 화면에서 검토한 코드와 실제로 실행되는 코드가 다를 수 있다는 뜻입니다.

발견된 MCP 서버의 실행 명령은 해당 repository의 README에서 추출합니다. README는 repository 소유자가
작성한 문서이며 검증된 manifest가 아니므로, 추출된 명령은 주장으로 취급합니다. npm으로 실행되는
서버는 추천 전에 registry에 조회하여 다음을 확인합니다.

- 패키지가 실제로 존재하는가
- 패키지가 선언한 repository가 후보를 발견한 repository와 일치하는가 — repository 소유권과 npm 패키지
  소유권을 연결하는 유일한 지점입니다
- 고정할 버전 — README가 `@latest`를 쓰더라도 registry가 보고한 버전으로 대체합니다

세 가지 중 하나라도 확인되지 않으면 해당 후보는 추천하지 않으며, 제외 사유에 어느 쪽이 실패했는지
기록합니다. HTTP MCP 서버는 고정할 버전이 존재하지 않으므로 이 규칙의 대상이 아니고, README에서
추출됐다는 경고만 표시합니다.

Risk 분석은 README에서 추출된 실행 명령(`install.readme_derived`, `WARNING`), 고정된 버전
(`install.version_pinned`, `LOW`), commit이 아닌 branch를 따라가는 설치를 각각 보고합니다.

## Outbound network

Agent Guidance가 직접 접속하는 호스트는 다음뿐입니다.

- `api.github.com` — component 탐색. `GITHUB_TOKEN` 또는 `GH_TOKEN`이 있으면 사용합니다
- `registry.npmjs.org` — npm MCP 서버의 패키지 존재 여부와 버전 확인. **Credential을 전송하지
  않습니다.** GitHub client와 분리된 HTTP client를 사용하며, 이는 사용자 GitHub token이 제3자에게
  전달되지 않도록 하기 위한 의도적 분리입니다
- Component repository의 `git clone` 대상 호스트 (일반적으로 `github.com`)

`agent-guidance setup --offline`은 위 접속을 전부 생략하고 내장 Registry와 검증된 cache만 사용합니다.

## Credentials

Credential 값은 CLI Plan, cache, state, event log, debug bundle에 저장하지 않습니다. Agent 설정에는
가능한 경우 환경변수 참조만 기록합니다. JSONL log와 debug info는 알려진 secret key와 Bearer token을
redact합니다.

## Backup and rollback

모든 선택 Agent의 설정을 첫 변경 전에 `~/.agent-guidance/backups/<transaction-id>/`에 백업합니다. 설치 중
치명적 Health Check가 실패하면 전체 Agent를 역순으로 rollback합니다. Agent Guidance marker가 없는 사용자
기존 Skill/Plugin 경로는 제거하지 않습니다. rollback 자체가 일부 실패하면 정확한 오류 목록을
manifest와 CLI에 남깁니다.

설치 이후 사용자가 수정한 Agent Guidance 관리 파일은 저장된 SHA-256과 달라집니다. `agent-guidance
uninstall`은 이 차이를 확인하고 사용자가 수정한 파일을 삭제하지 않으며, 남긴 경로를 알려줍니다.

## Supported versions and boundaries

보안 수정은 최신 Release Candidate와 최신 안정 릴리스(게시된 경우)를 대상으로 합니다. Agent Guidance는
외부 Skill/MCP/Plugin의 동작, upstream compromise, Agent 자체 sandbox 또는 credential 보관소를
통제하지 않습니다. 관리자/root 권한을 자동 요청하지 않으며 system-wide runtime을 설치하지 않습니다.

상세 위협과 잔여 위험은 [docs/threat-model.md](docs/threat-model.md)를 참고하십시오.

## Reporting a vulnerability

공개 Issue에 token, 설정 원문, backup, private repository URL을 첨부하지 마십시오. 재현 절차,
영향받는 Agent Guidance version, 운영체제, sanitized `agent-guidance debug-info` 출력만 포함해 repository maintainer의
비공개 보안 연락 경로로 보고하십시오.
