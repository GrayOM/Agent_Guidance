# GrayOM Agent Guidance Architecture

## 1. 목표

GrayOM Agent Guidance는 이미 설치된 AI Agent 환경을 감지하고 사용자의 업무 선택으로부터 필요한
기능을 추론해 Skill, MCP, Plugin 구성을 추천·설치·검증하는 CLI 도구다. 일반 개발환경이나 Agent
자체를 설치하지 않으며 사용자 승인 전에는 Agent 설정을 변경하지 않는다.

## 2. MVP 범위

MVP는 Codex의 end-to-end 흐름에 집중한다.

- Typer/Rich/InquirerPy 기반 CLI와 GrayOM 로고
- Codex 실행 파일 및 설정 경로 감지
- 업무 분야와 세부 작업 복수 선택, Minimal/Performance 모드
- deterministic capability inference
- 로컬 YAML Registry 기반 추천
- 역할 중복, 설정 대상, 도구 이름, 권한 및 context 부담 분석
- LOW/WARNING 보안 결과와 선택·제외 근거 출력
- 승인 직후 설정 백업, Skill/MCP 설치, Health Check, 실패 시 자동 Rollback

Claude Code/Cursor 실제 설치, LLM 추천, 범용 인증 자동화는 MVP 이후다.

Codex Skill은 사용자 범위인 `$HOME/.agents/skills`에 설치한다. 외부 저장소는 Registry에 고정된
commit SHA만 checkout하고 `SKILL.md` frontmatter 및 symlink 부재를 검증한다. MCP는 기존
`~/.codex/config.toml`을 `tomlkit`으로 보존 병합하며 인증 비밀값 대신 환경변수 이름만 기록한다.

## 3. 계층

| 계층 | 책임 |
|---|---|
| `cli` | 인터뷰, Plan 렌더링, 단일 승인, 명령 라우팅 |
| `core` | capability 추론, 추천, 충돌·보안 분석, 설치 트랜잭션 |
| `adapters` | Agent 감지, 조사, 백업, 설치, 검증, 복구 |
| `models` | 단계 간 Pydantic 계약 |
| `registry` | 검증된 후보와 업무-capability 규칙 |
| `sources` | Registry·공식·GitHub 수집, 정규화, 검증, 보안 증거, 캐시 |

의존성 방향은 `cli -> core -> models`, `core -> adapters`, `core -> registry`로 제한한다.

## 3.1 실시간 후보 탐색

추천 후보는 Local Registry, 검증된 공식 프로젝트 catalog, GitHub 검색 결과를 합쳐 만든다.

1. 선택 Agent와 capability로 Skill/MCP/Plugin 검색 쿼리를 생성한다.
2. GitHub 메타데이터, README, release, repository tree와 설치 관련 파일을 수집한다.
3. 모든 결과를 공통 `Component` 모델로 정규화한다.
4. Trust, Maintenance, Agent compatibility, install method, dependency를 검증한다.
5. repository 파일 증거로 보안 metadata와 evidence를 만든다.
6. 동일 repository 후보는 공식 → curated registry → verified community 순으로 병합한다.
7. API 실패 시 Local Registry와 verified cache로 계속 추천한다.

캐시는 검색 자체를 생략하는 영구 catalog가 아니다. 검색 결과의 `pushed_at`이 같을 때만 TTL 안의
정규화 결과를 재사용하며 신규 검색은 계속 수행한다. GitHub 토큰은 환경변수로만 읽고 캐시나
로그에 기록하지 않는다.

## 4. 실행 흐름

1. 읽기 전용으로 Agent를 감지하고 현재 상태를 조사한다.
2. 사용자가 Agent, 업무, 세부 작업, 구성 모드를 선택한다.
3. 선택값을 내부 capability 집합으로 변환한다.
4. Registry 후보를 호환성 및 capability coverage로 필터링한다.
5. 모드별 점수로 후보를 선택하고 제외 근거를 기록한다.
6. Skill/MCP/Plugin 상호 간 중복과 충돌을 분석한다.
7. 권한·shell·network·credential·destructive 동작을 LOW/WARNING으로 분류한다.
8. 전체 Plan을 한 번에 출력하고 한 번만 승인받는다.
9. 승인 직후 설정과 설치 목록을 백업하고 변경을 적용한다.
10. Health Check 실패 시 부분 설치를 제거하고 원본을 복원한다.

## 5. 추천 규칙

사용자에게 MCP나 브라우저 같은 구현 수단을 묻지 않는다. `domain + task` 규칙이 capability를
생성하며 후보의 `capabilities`와 교차해 coverage를 계산한다. Minimal은 적은 구성요소, 낮은 context
비용, 낮은 중복을 우선한다. Performance는 전문 coverage와 품질을 우선하고 일부 중복을 허용한다.
모든 선택 및 제외 결과에는 사람이 읽을 수 있는 이유가 필요하다. 추천 정책은 필수 조건
(Agent 호환성, 검증 상태, 설치 가능성), 우선 조건(capability coverage, official/trust,
maintenance), tie-breaker(context cost, 설치 복잡도, 품질, stars) 순으로 판단한다.

## 6. 충돌 및 보안

충돌 분석은 종류가 같은 후보뿐 아니라 Skill-MCP 및 Plugin 내부 구성과 외부 구성도 비교한다.
동일 capability, tool 이름, 설정 파일, 강제 workflow, 권한 범위를 확인한다. 보안 결과의 공개 등급은
LOW와 WARNING만 사용한다. WARNING은 차단하지 않으며 최종 Plan에 표시한다.

## 7. Adapter 계약

모든 Adapter는 `detect`, `inspect`, `backup`, `install_skill`, `configure_mcp`, `install_plugin`,
`health_check`, `rollback`을 제공한다. 동일 MCP 구현과 설치 자산은 재사용할 수 있지만 각 Agent의
등록 형식은 해당 Adapter가 책임진다.

## 8. 트랜잭션과 Rollback

설치는 `prepare -> backup -> apply -> verify -> commit` 순서다. 변경마다 manifest에 원본 경로,
백업 경로, 생성 항목을 기록한다. 실패하면 역순으로 생성 항목을 제거하고 백업을 복원한다.
백업 생성은 사용자 승인 직후 수행하므로 승인 전 쓰기 금지 원칙을 유지한다.

## 9. Health Check

단순 존재 여부 외에 설정 구문 파싱, 실행 명령 해석, Skill discovery 경로, 중복 등록을 검사한다.
STDIO MCP는 실행 명령 해석을 검사한다. HTTP MCP는 인증 환경변수가 설정된 경우 initialize와
`tools/list`를 호출한다. 네트워크·인증 문제는 WARNING으로 표시하되 설정 파싱, 설치된 Skill
discovery, MCP 등록 누락 같은 치명적 실패는 전체 설치를 Rollback한다.
