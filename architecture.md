# GrayOM Agent Guidance Architecture

## 1. 목적과 경계

GrayOM Agent Guidance는 이미 설치된 AI Agent를 감지하고 사용자의 업무 선택에서 필요한 capability를
추론해 Skill, MCP, Plugin을 추천·설치·검증하는 CLI다. Agent, IDE, Node.js, Python, Docker, Git 등
일반 개발환경은 설치하지 않으며 최종 일괄 승인 전에는 Agent 설정이나 backup을 만들지 않는다.

지원 Agent는 Codex와 Claude Code다. 하나의 업무 Profile로 전체 후보를 추천한 뒤 실제 적용은
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
| Claude Code | `~/.claude/skills` | `~/.claude.json`의 `mcpServers` | `claude plugin` CLI 위임 (marketplace ID 없으면 `PARTIAL`) |

설정은 read → parse → merge → validate → fsync → atomic replace 순으로 쓴다. 같은 MCP 이름에 다른
구현이 있으면 사용자 설정을 보존하고 가능한 경우 `-grayom` 별칭을 사용한다.

Plugin은 설정 키가 아니다. `settings.json`의 `enabledPlugins`는 이미 설치된 Plugin을 켜고 끄는
스위치일 뿐이고, 실제 설치는 marketplace 등록 → 아카이브 수신 → manifest 검증 → `~/.claude/plugins/cache`
전개로 이루어지며 marketplace가 선언한 명령을 실행할 수도 있다. 그 신뢰 모델을 재구현하지 않고
Claude Code의 `claude plugin` 명령에 위임한 뒤 GrayOM 트랜잭션으로 감싼다. 각 단계에 역연산이
있으므로 되돌릴 수 있다.

| 단계 | 역연산 |
|---|---|
| `claude plugin marketplace add` | `claude plugin marketplace remove` |
| `claude plugin install` | `claude plugin uninstall` |

이 실행에서 추가한 것만 기록하고 되돌린다. 사용자가 이미 가지고 있던 marketplace는 제거하지 않고,
이미 설치된 Plugin은 보존한다. Rollback은 Plugin을 먼저 제거한다(해당 Plugin이 남아 있으면
marketplace를 제거할 수 없다). `--yes`, `--accept-command`는 절대 전달하지 않는다. marketplace가
선언한 명령의 수락은 사용자의 결정이므로, 승인이 필요한 Plugin은 그 사실을 보고하고 건너뛴다. 되돌린 뒤 Claude Code의
`installed_plugins.json`, `known_marketplaces.json`, `marketplaces/`는 모두 원상태로 돌아간다.
`plugins/cache/` 아래 디렉터리는 Claude Code가 `.orphaned_at` 표시만 남기고 보관하며, GrayOM
관리 root 밖이라 직접 삭제하지 않는다.

후보는 저장소의 `.claude-plugin/marketplace.json`에서 marketplace 이름과 Plugin 이름을 읽어
`<plugin>@<marketplace>` 설치 ID를 만든다. manifest가 없으면 `PLUGIN_GIT`으로 기록하고 이유를
밝혀 거부한다. `SKILL.md`가 있는 저장소는 marketplace가 있어도 Skill로 취급한다. Plugin으로
설치하면 번들된 Skill이 전부 적재되어 Skill 선별이 막으려는 context 비용이 그대로 발생한다.

## 4. 후보 탐색과 검증

1. 선택 Agent와 capability로 bounded query를 만든다.
2. Local Registry는 항상 읽고 공식 catalog와 GitHub를 실시간 확인한다.
3. metadata, README, release, tree, install/manifest 파일을 공통 `Component`로 정규화한다.
4. trust, maintenance, license, install method, dependency와 Agent evidence를 검증한다.
5. repository 파일 증거로 shell, subprocess, network, credential, write/delete, install/update script를 검사한다.
6. 동일 repository는 official → Registry → verified community → cache 순으로 결정적으로 병합한다.
   단 marketplace plugin은 repository가 아니라 설치 ID(`<plugin>@<marketplace>`)로 식별한다.
   한 marketplace repository가 서로 다른 plugin 여러 개를 발행하기 때문이다.
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

Skill 저장소는 Skill 하나가 아니다. 저장소 안에서 설치할 Skill은 네 규칙으로 좁힌다.

1. 이번 실행이 요청한 capability를 말하는 Skill만 남긴다
2. 이미 선택한 Skill과 이름이나 목적이 겹치면 버린다
3. 저장소의 한 하위 프로젝트가 예산의 1/3을 넘게 가져가지 못한다
4. mode 한도까지, 일치도가 높은 순으로 멈춘다

3번은 2번이 놓치는 것을 잡는다. `trailofbits/skills`에서 CVE 분석과 OSS 취약점 연구를 선택하면
`building-secure-contracts`가 Performance 12칸 중 7칸을 플랫폼별 smart contract 스캐너로 채웠다.
여섯 스캐너는 같은 일을 여섯 번 설명한 것이지만 설명마다 다른 플랫폼 이름을 쓰기 때문에 단어 겹침으로는
같다고 판정되지 않는다. 저장소 자신의 디렉터리 그룹이 이미 그 묶음을 선언하고 있으므로 그것을 쓴다.
그룹이 없는 평평한 저장소는 전체가 한 그룹으로 묶여 두 개만 설치되는 일이 없도록 배분하지 않는다.

저장소가 발행하지 않은 `SKILL.md`는 후보가 아니다. `tests`, `fixtures`, `node_modules` 같은 경로
아래의 `SKILL.md`는 저장소의 테스트 데이터이며, 실제로 `trailofbits/skills`의 85개 중 2개가 여기에
해당해 그중 하나가 보안 요청에서 19위로 올라왔다.

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

Manifest에는 원본/사후 hash, backup, 생성 경로, 설치/기존 component, shared ownership, 그리고 이
실행이 추가한 Plugin과 marketplace를 기록한다.
Rollback은 GrayOM marker가 있고 Adapter 관리 root 안에 있는 경로만 제거한다. 일부 rollback 실패는
숨기지 않고 Agent별 오류를 남긴다.

Mutating command는 `~/.grayom/grayom.lock`을 원자적으로 획득한다. 다음 setup은 미완료 transaction을
탐지해 새 변경 전에 rollback을 우선하며, live PID lock은 거부하고 stale lock만 회수한다.

Codex는 config parse, Skill discovery, MCP 등록/command/endpoint와 선택적 HTTP initialize/tools/list를
검사한다. Claude Code는 JSON parse, marker discovery, MCP endpoint/command를 검사하고, Plugin은
`claude plugin list`로 설치 여부(치명적)와 활성화 여부(경고)를 따로 본다. 설치되었지만 꺼져 있는
상태는 설치 실패와 다르기 때문이다. `claude`를 실행할 수 없으면 그 사실 자체를 경고로 남긴다.
수행할 수 없는 검사는 성공으로 추측하지 않는다.

## 9. CLI와 운영 데이터

`grayom`은 interactive menu, `setup/recommend/doctor/update/rollback/debug-info`는 direct command다.
`--help`와 `--version`은 discovery나 Agent 진단을 수행하지 않는다. `setup --dry-run`은 Plan까지
실행하되 backup, config, state를 만들지 않는다.

`GRAYOM_HOME` 또는 기본 `~/.grayom` 아래에 `config.yaml`, `cache/`, `backups/`, `logs/`, `state/`를
둔다. JSONL event log와 debug bundle은 credential key와 Bearer token을 redact한다.

## 10. Update 범위

`grayom update`는 `EXISTING`을 제외한 GrayOM-managed component만 대상으로 한다. 비교 기준은
upstream이 현재 publish하는 ref이며, 고정 방식을 따라 commit pin은 default branch head commit,
tag pin은 최신 release와 비교한다. upstream을 확인할 수 없는 component는 unchanged가 아니라
미확인으로 보고하고 Local Registry의 검증된 source ref로 비교를 대체한다. `--offline`은 upstream
확인 없이 Registry만 사용한다.

Update 전 backup, 적용 후 Health Check, 실패 시 asset/config 복구를 수행한다. 저장 hash와 달라진
사용자 수정 파일은 승인 전에 경고한다. 실제 version migration은 후속 범위이며
state/cache/manifest는 schema version 1과 미래 schema 거부를 지원한다.
