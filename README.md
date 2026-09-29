# GrayOM Agent Guidance

업무 중심 인터뷰로 AI Agent용 Skill, MCP, Plugin을 추천하고 기존 Agent 환경에 안전하게 적용하는 CLI입니다.

## What is GrayOM Agent Guidance?

GrayOM은 사용자가 Skill이나 MCP 구현을 직접 고르게 하지 않습니다. 선택한 Agent, 업무 분야, 세부
작업에서 필요한 capability를 결정적으로 추론하고 Local Registry, 공식 프로젝트, GitHub 후보를
검증합니다. 이후 호환성, 중복, 충돌, 유지보수 상태, 권한과 보안 신호를 분석해 Agent별 변경 Plan을
만듭니다.

GrayOM은 Agent나 Node.js, Python, Docker, Git, IDE를 설치하지 않습니다. 이미 설치된 Agent의 AI
확장 환경만 관리합니다.

## Supported Agents

- Codex
- Claude Code
- Cursor

Agent별 지원 범위가 다르면 지원되는 Agent에만 적용합니다. `UNKNOWN` 호환성을 자동으로
`SUPPORTED`로 취급하지 않습니다.

## Features

- 업무/세부 작업 복수 선택과 Minimal/Performance 모드
- Local Registry, 공식 catalog, GitHub 실시간 후보 탐색과 검증 캐시
- 결정적 capability inference와 추천 근거 설명
- Agent별 compatibility 및 version requirement 분석
- Skill/MCP/Plugin 중복, capability overlap, config/tool/path 충돌 분석
- LOW/WARNING 보안 검토와 repository 정적 증거
- shared MCP 1회 준비 및 Agent별 설정 참조
- 기존 구성 reconciliation과 반복 실행 idempotency
- 모든 Agent 선백업 후 적용하는 전역 transaction
- 통합 Health Check와 전체 rollback
- GrayOM-managed component update
- dry-run, doctor, sanitized debug info, JSONL event log

## Installation

Python 3.11 이상과 대상 Agent가 먼저 설치되어 있어야 합니다.

```bash
pipx install .
```

개발 환경:

```bash
python -m pip install -e '.[dev]'
python -m pytest
```

## Usage

```bash
grayom                 # interactive menu
grayom setup           # recommend, approve once, install, verify
grayom setup --dry-run # no backup or mutation
grayom recommend       # Plan only
grayom doctor          # read-only diagnosis
grayom update          # GrayOM-managed components only
grayom rollback        # latest transaction
grayom debug-info      # sanitized diagnostic JSON
grayom --version
```

네트워크 없이 Registry와 검증 캐시만 사용하려면:

```bash
grayom setup --offline
grayom recommend --offline
```

GitHub API 인증은 환경변수로만 제공합니다.

```bash
export GITHUB_TOKEN="..."
export GITHUB_PAT_TOKEN="..."  # GitHub MCP가 요구하는 경우
```

## Example

`Codex + Claude Code + Cursor`, `Security Tool Development`, `Source Code Analysis`, `Minimal`을
선택하면 GrayOM은 필요한 capability를 추론하고 전체 후보를 추천한 뒤 Agent별 지원 여부를 다시
평가합니다. 공통 MCP는 한 번 준비하고 각 Agent의 공식 설정 포맷에 별도로 등록합니다. 설치 승인은
Plan 전체에 대해 한 번만 받습니다.

## Configuration and State

GrayOM 데이터는 기본적으로 `~/.grayom/` 아래에 저장합니다.

```text
~/.grayom/
├── config.yaml
├── cache/
├── backups/
├── logs/
└── state/
```

`GRAYOM_HOME`으로 위치를 바꿀 수 있습니다. 업무 Profile 전체는 저장하지 않습니다. state에는
GrayOM이 관리하는 component ID, Agent 사용 관계, ownership, source ref, transaction 참조만
저장합니다.

## Security Model

- 승인 전 Agent 설정을 수정하거나 backup을 만들지 않습니다.
- 설정은 parse → merge → validate → atomic replace 순서로 처리합니다.
- 사용자 기존 component와 충돌하는 MCP 이름은 보존하고 안전한 `-grayom` 별칭을 사용합니다.
- rollback은 GrayOM marker와 manifest로 소유권이 확인된 경로만 제거합니다.
- token, password, OAuth 값, SSH key, `.env` secret은 state/log에 저장하지 않습니다.
- WARNING은 차단 등급이 아니며 최종 Plan에 근거와 함께 표시합니다.

자세한 내용은 [SECURITY.md](SECURITY.md)를 참고하십시오.

## Supported Platforms

Linux, macOS, Windows의 사용자 home 경로를 `pathlib`으로 처리합니다. WSL은 감지하지만 WSL에서
Windows 호스트에 설치된 Cursor 설정을 추측해 수정하지 않고 경고만 표시합니다.

## Limitations

- Claude Code Plugin은 검증된 marketplace 식별자 없이 임의 Git URL만으로 자동 설치하지 않습니다.
- Cursor local Plugin은 공식 manifest가 있는 Git repository만 지원합니다.
- Codex는 HTTP MCP initialize/tool discovery를 시도할 수 있지만 Claude Code/Cursor의 현재 Health
  Check는 설정 parse, discovery metadata, endpoint/command 유효성 중심입니다.
- `grayom update`는 현재 Local Registry의 검증된 ref 변경을 기준으로 동작합니다. live upstream
  release 비교와 자동 migration은 후속 범위입니다.
- WSL과 Windows host 사이의 cross-environment 설정 변경은 지원하지 않습니다.
- 새 추천에서 제외된 기존 GrayOM component를 자동 삭제하지 않습니다.

## Development

```bash
python -m compileall -q src tests
python -m pytest -q --cov=grayom_agent_guidance
```

Architecture는 [architecture.md](architecture.md)에 정리되어 있습니다.

## License

MIT
