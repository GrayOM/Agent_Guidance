# GrayOM Agent Guidance Architecture

## 1. 목적과 경계

GrayOM Agent Guidance는 이미 설치된 AI Agent를 감지하고 사용자의 업무 선택에서 필요한 capability를
추론해 Skill, MCP, Plugin을 추천·설치·검증하는 CLI다. Agent, IDE, Node.js, Python, Docker, Git 등
일반 개발환경은 설치하지 않으며 최종 일괄 승인 전에는 Agent 설정이나 backup을 만들지 않는다.

지원 Agent는 Codex, Claude Code, Cursor다. 하나의 업무 Profile로 전체 후보를 추천한 뒤 실제 적용은
Component × Agent compatibility를 다시 계산해 지원되는 Agent에만 수행한다.

## 2. 계층

| 계층 | 책임 |
|---|---|
| `cli` | 대화형 메뉴, 인터뷰, Plan, 단일 승인, direct command |
| `core` | inference, recommendation/explanation, compatibility, reconcile, conflict/security, transaction/update |
| `adapters` | Agent 감지, inventory, backup, Agent별 설치/설정, Health Check, rollback |
| `models` | 단계 간 Pydantic 계약과 ownership/compatibility 상태 |
| `registry` | 검증된 후보와 고정 install ref |
| `sources` | Registry·공식·GitHub 수집, 정규화, 검증, 보안 증거, cache |
| `network` | timeout, proxy 환경, User-Agent를 포함한 공통 HTTP client |
| `runtime` | `shell=False` process runner, timeout/redaction, path validation, operation lock |
| `state` | GrayOM ownership, Agent 사용 관계, source/ref/path/hash, transaction 참조 |

CLI 입력은 `InterviewAnswer`로 core에 전달하며 core에서 `input()`을 호출하지 않는다.

## 3. Agent Adapter 계약

모든 Adapter는 다음 공통 interface를 구현한다.

- `detect`, `inspect`, `get_version`, `get_config_paths`
- `capabilities` (`skills`, `mcp`, `plugins`, `config_merge`, `health_probe`)
- `list_existing_skills`, `list_existing_mcps`, `list_existing_plugins`
- `backup`, `install_skill`, `configure_mcp`, `install_plugin`
- `health_check`, `rollback`

Agent별 사용자 범위는 공식 문서에 근거한다.

| Agent | Skill | MCP | Plugin |
|---|---|---|---|
| Codex | `~/.agents/skills` | `CODEX_HOME/config.toml` 또는 `~/.codex/config.toml` | 자동 설치 제외 |
| Claude Code | `~/.claude/skills` | `~/.claude.json`의 `mcpServers` | marketplace ID 없으면 `PARTIAL` |
| Cursor | `~/.cursor/skills` | `~/.cursor/mcp.json` | 공식 Marketplace/API 방식 미확정으로 자동 설치 제외 |

설정은 read → parse → merge → validate → fsync → atomic replace 순으로 쓴다. 같은 MCP 이름에 다른
구현이 있으면 사용자 설정을 보존하고 가능한 경우 `-grayom` 별칭을 사용한다.

## 4. 후보 탐색과 검증

1. 선택 Agent와 capability로 bounded query를 만든다.
2. Local Registry는 항상 읽고 공식 catalog와 GitHub를 실시간 확인한다.
3. metadata, README, release, tree, install/manifest 파일을 공통 `Component`로 정규화한다.
4. trust, maintenance, license, install method, dependency와 Agent evidence를 검증한다.
5. repository 파일 증거로 shell, subprocess, network, credential, write/delete, install/update script를 검사한다.
6. 동일 repository는 official → Registry → verified community → cache 순으로 결정적으로 병합한다.
7. API/timeout/rate-limit 실패 시 Registry와 verified cache로 계속한다.

Cache는 영구 catalog가 아니다. live search는 계속 수행하며 source version과 TTL이 모두 맞을 때만
정규화 결과를 재사용한다. GitHub token 값은 cache/log/state에 저장하지 않는다.

## 5. 추천과 설명

`domain + detailed task` 규칙이 capability를 생성한다. 추천은 다음 순서로 결정한다.

1. required capability coverage
2. selected Agent compatibility
3. official/verified source
4. active maintenance
5. lower conflict/overlap
6. lower context cost
7. simpler install
8. stable component ID

같은 입력·Registry·환경이면 GitHub 검색 순서와 무관하게 같은 결과를 만든다. Minimal은 최소 component와
낮은 중복을, Performance는 전문 coverage를 우선한다. 각 추천은 입력 업무, 담당 capability, 선택 이유,
적용 Agent, 제한사항과 evidence confidence를 갖는다. 충족되지 않은 capability는 Plan에 명시한다.

## 6. Compatibility와 reconciliation

Compatibility 상태는 `SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, `UNKNOWN`이다. Adapter capability가
false인 component type은 설치 Plan에서 `UNSUPPORTED`로 제외한다. version requirement가
있는데 Agent version을 확인할 수 없으면 `UNKNOWN`이며 자동 설치하지 않는다. Agent 하나에서
미지원이어도 다른 Agent의 지원되는 적용은 유지한다.

현재 환경과 추천 환경을 비교해 `UNCHANGED`, `ADD`, `UPDATE`, `REFERENCE`, `SKIP`, `CONFLICT`를
만든다. 반복 setup은 동일 component를 다시 설치하거나 설정을 다시 쓰지 않는다. 새 추천에서 빠진
기존 GrayOM component는 자동 삭제하지 않는다.

## 7. Shared component와 ownership

동일 MCP runtime requirement는 `SharedComponentManager`가 한 번만 준비하고 각 Adapter가 자기 설정에
참조를 등록한다. HTTP MCP는 설치 자산 없이 endpoint를 공유하며 STDIO dependency는 존재 여부만
검사하고 runtime 자체를 설치하지 않는다.

Ownership은 `EXISTING`, `GRAYOM_INSTALLED`, `GRAYOM_MODIFIED`, `SHARED`다. `EXISTING` component는
update나 rollback 삭제 대상이 아니다. State에는 component ID, source ref, 사용 Agent, ownership,
transaction 참조, 설치 경로와 SHA-256을 저장하고 업무 Profile과 secret은 저장하지 않는다.

## 8. Transaction, Health Check, rollback

Multi-Agent 설치는 `PREPARED → BACKING_UP → APPLYING → VERIFYING → COMMITTED` 상태로 기록한다.
실패하면 `ROLLING_BACK → ROLLED_BACK`이며 rollback 오류가 있으면 `FAILED`다. 순서는 다음과 같다.

1. 모든 선택 Agent backup
2. shared component 1회 준비
3. Agent별 변경 적용
4. 모든 Agent Health Check
5. 모두 성공하면 commit
6. 하나라도 치명적으로 실패하면 전체 Agent 역순 rollback

Manifest에는 원본/사후 hash, backup, 생성 경로, 설치/기존 component, shared ownership을 기록한다.
Rollback은 GrayOM marker가 있고 Adapter 관리 root 안에 있는 경로만 제거한다. 일부 rollback 실패는
숨기지 않고 Agent별 오류를 남긴다.

Mutating command는 `~/.grayom/grayom.lock`을 원자적으로 획득한다. 다음 setup은 미완료 transaction을
탐지해 새 변경 전에 rollback을 우선하며, live PID lock은 거부하고 stale lock만 회수한다.

Codex는 config parse, Skill discovery, MCP 등록/command/endpoint와 선택적 HTTP initialize/tools/list를
검사한다. Claude Code/Cursor는 JSON parse, marker discovery, MCP endpoint/command를 검사한다. 수행할
수 없는 검사는 성공으로 추측하지 않는다.

## 9. CLI와 운영 데이터

`grayom`은 interactive menu, `setup/recommend/doctor/update/rollback/debug-info`는 direct command다.
`--help`와 `--version`은 discovery나 Agent 진단을 수행하지 않는다. `setup --dry-run`은 Plan까지
실행하되 backup, config, state를 만들지 않는다.

`GRAYOM_HOME` 또는 기본 `~/.grayom` 아래에 `config.yaml`, `cache/`, `backups/`, `logs/`, `state/`를
둔다. JSONL event log와 debug bundle은 credential key와 Bearer token을 redact한다.

## 10. Update 범위

`grayom update`는 `EXISTING`을 제외하고 Local Registry의 검증된 source ref가 달라진 GrayOM-managed
component만 대상으로 한다. Update 전 backup, 적용 후 Health Check, 실패 시 asset/config 복구를
수행한다. 저장 hash와 달라진 사용자 수정 파일은 승인 전에 경고한다. Live upstream release 비교와
실제 version migration은 후속 범위이며 state/cache/manifest는 schema version 1과 미래 schema 거부를
지원한다.
