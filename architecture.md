# GrayOM Agent Guidance — Architecture

> 상태: **설계 초안 (v0.1, 구현 전 승인 대기)**
> 범위: AI Agent(Codex / Claude Code / Cursor) 환경 설정 전용 CLI. 개발환경 자체는 건드리지 않는다.

---

## 1. 제품 정의

| 항목 | 내용 |
|---|---|
| 입력 | 사용 Agent(복수), 업무 도메인(복수), 세부 작업(복수), 구성 모드(Minimal/Performance) |
| 내부 처리 | Capability 추론 → 후보 수집 → 점수화/선택 → 충돌·중복 분석 → 보안 검사 |
| 출력 | 설치 Plan 1회 출력 → 일괄 승인(Y/N) → 설치 → Health Check → 실패 시 Rollback |
| 비목표 | Agent 자체 설치, Docker/Node/Python 설치, Web UI, Gemini CLI, 사용자 프로필 저장 |

사용자는 “GitHub MCP가 필요한가?” 같은 기술 질문을 받지 않는다. 기술 판단은 전부 `capability_inference` + `recommender`가 한다.

---

## 2. 전체 데이터 흐름

```
 grayom setup
   │
   ├─(1) detect      adapters/*.detect()              ── read-only
   ├─(2) inspect     adapters/*.inspect()             ── read-only (현재 설치된 Skill/MCP/Plugin 목록)
   ├─(3) interview   cli/interview.py → InterviewResult
   ├─(4) collect     sources/registry(+cache,+github) → list[Component]
   ├─(5) infer       core/capability_inference.py     → set[Capability] (+근거)
   ├─(6) recommend   core/recommender.py              → Selection(선택/스킵/이유)
   ├─(7) conflict    core/conflict.py                 → list[ConflictFinding]
   ├─(8) security    core/security.py                 → list[RiskFinding], overall LOW|WARNING
   ├─(9) plan        models/recommendation.InstallPlan → cli/ui.render_plan()
   ├─(10) approve    [Y] Install / [N] Cancel          ── 여기까지 Agent 설정 무수정
   ├─(11) backup     adapters/*.backup()  → ~/.grayom/backups/<ts>/ + manifest.json
   ├─(12) install    core/installer.py → adapter.install_skill / configure_mcp / install_plugin
   ├─(13) health     adapters/*.health_check() → HealthReport
   ├─(14) rollback   실패 시 core/rollback.py → adapter.rollback(manifest)
   └─(15) result     cli/ui.render_result()
```

> ⚠️ 요구사항의 설치 흐름은 “2. 기존 설정 백업”이 인터뷰 전에 있다. 본 설계는 **백업을 승인 직후(11)** 로 옮겼다. 사유는 §10 C-1 참고.

---

## 3. 레이어 구조와 책임

| 레이어 | 모듈 | 책임 | 부작용 |
|---|---|---|---|
| CLI | `cli/main.py` | Typer 엔트리포인트 (`grayom`, `setup`, `recommend`, `doctor`, `rollback`) | 없음 |
| | `cli/interview.py` | InquirerPy 선택형 인터뷰 → `InterviewResult` | 없음 |
| | `cli/ui.py` | Rich 렌더링 (로고, Plan, 결과) | stdout |
| Core | `core/capability_inference.py` | 업무/세부작업 → Capability (YAML 규칙, deterministic) | 없음 |
| | `core/recommender.py` | 후보 점수화, 역할별 1개 선택(Minimal) / 전문 후보 추가(Performance) | 없음 |
| | `core/conflict.py` | 11종 충돌 규칙 검사 | 없음 |
| | `core/security.py` | 정적 위험 신호 탐지, 업무별 가중치, LOW/WARNING 산정 | 없음 (다운로드한 소스 **읽기만**) |
| | `core/installer.py` | Plan 실행 오케스트레이션, 단계별 manifest 기록 | Agent 설정 수정 |
| | `core/rollback.py` | manifest 기반 복원/부분 설치 제거 | Agent 설정 복원 |
| | `core/health.py` | Adapter health 결과 집계 | MCP 프로세스 기동(검증용) |
| Adapter | `adapters/base.py` | 공통 인터페이스 (ABC) | — |
| | `adapters/codex.py` | Codex 전용 경로/포맷/검증 | Codex 설정만 |
| Source | `sources/registry.py` | 로컬 `registry/*.yaml` 로드·검증 | 없음 |
| | `sources/official.py`, `github.py` | 실시간 후보 탐색 (MVP 이후) | 네트워크 |
| | `sources/cache.py` | 컴포넌트 메타데이터/검증 결과 캐시 (사용자 정보 저장 안 함) | `~/.grayom/cache/` |
| Model | `models/*.py` | Pydantic v2 모델 | 없음 |

**원칙:** Core의 추천·분석 계층은 순수 함수로 유지하고, 부작용은 `installer`/`rollback`/`adapter`에만 둔다. → 테스트 용이, `grayom recommend`는 무부작용 보장.

---

## 4. 데이터 모델 (Pydantic v2)

```
AgentKind        = codex | claude_code | cursor
ComponentType    = skill | mcp | plugin
Mode             = minimal | performance
RiskLevel        = LOW | WARNING            # 2단계만 존재
Domain / Task    = Enum (인터뷰 선택지와 1:1)
Capability       = Enum (dev_workflow, repo_access, security_analysis, test_execution,
                         report_support, browser_automation, web_research, ... )
```

| 모델 | 주요 필드 |
|---|---|
| `AgentInstallation` | kind, detected, version, binary_path, config_dir, config_files, installed_components |
| `Component` | id, name, type, publisher, official, source_url, agents(호환), provides(Capability 목록), roles(역할 태그), install(설치 스펙, Agent별), permissions, context_cost(low/med/high), license, stars, last_updated, bundled(Plugin 내부 Skill/MCP id), workflow(강제하는 workflow 식별자), tool_names, config_targets |
| `InstallSpec` | method(git_clone/copy/npx/uvx/docker/remote_url), ref(고정 커밋/태그), command/args/env_keys(값 아님), target_subdir |
| `InterviewResult` | agents, domains, tasks, mode |
| `CapabilityNeed` | capability, reasons(어떤 domain/task 때문인지) |
| `Selection` | selected: list[SelectedComponent(component, reason, score)], skipped: list[SkippedComponent(component, reason, superseded_by)] |
| `ConflictFinding` | kind(11종), components, detail, resolution |
| `RiskFinding` | component_id, category, level, evidence(파일:라인 or 설정 키), weighted_by(domain) |
| `InstallPlan` | agents, mode, selection, conflicts, risks, overall_risk, notes, actions(list[PlannedAction]) |
| `PlannedAction` | agent, op(install_skill/configure_mcp/install_plugin), component_id, target_path |
| `BackupManifest` | id(ts), agents, files(원본경로→백업경로, sha256, existed), created_paths, applied_actions |
| `HealthCheck` / `HealthReport` | name, agent, ok, detail / checks, ok |

민감정보: `env_keys`에는 **환경변수 이름만** 저장하고 값은 저장·출력하지 않는다. 토큰은 설정 파일에 `${VAR}` 참조 또는 Agent가 지원하는 env 전달 방식으로만 기록.

---

## 5. 추천 엔진

### 5.1 Capability 추론 (`registry/capabilities.yaml`)
```yaml
domains:
  security_tool_development: [dev_workflow, security_analysis, repo_access, test_execution]
tasks:
  source_code_analysis:      [security_analysis, static_analysis, repo_access]
  security_report_automation:[report_support]
  ai_llm_security:           [security_analysis, ai_security]
```
- 결과는 `CapabilityNeed(capability, reasons=[...])` — Plan에 “왜 필요한지” 근거로 노출.
- LLM 추론 미사용 (MVP). 추후 AI 보조를 붙여도 최종 결정은 이 규칙으로 재검증.

### 5.2 점수화 (deterministic)
| 기준 | 가중치(초안) | 비고 |
|---|---|---|
| 공식 제작자 | +30 | `official: true` |
| Agent 호환 | 필수 필터 | 선택 Agent 중 1개 이상 미지원 시 해당 Agent 대상 action 제외 |
| 최근 업데이트 | +0~15 | 90일 이내 15, 1년 초과 0 |
| Star | +0~10 | log 스케일 |
| 문서 품질 | +0~5 | registry 수기 평가 |
| License | 0 / -10 | 미기재 -10 |
| Context 부담 | Minimal: low 0 / med -5 / high -15, Performance: 절반 |
| 필요 Capability 커버 수 | +10/개 | |

### 5.3 선택 알고리즘
- **Minimal:** 필요한 Capability를 최소 컴포넌트로 덮는 greedy set cover. 같은 `role`의 후보는 최고점 1개만 → 나머지는 `Skipped(reason="overlaps with X")`.
- **Performance:** Minimal 결과 + 각 Capability별 전문(`specialized: true`) 후보 추가. 역할 중복은 `workflow` 충돌이 없으면 허용하고 Plan에 “중복 허용” 표기.
- 동일 기능 MCP 복수 시 `official` 우선 (요구사항).

---

## 6. 충돌 분석 (`core/conflict.py`)

| # | 규칙 | 판정 근거 | 기본 처리 |
|---|---|---|---|
| 1 | Skill↔Skill | `roles` 교집합 | Minimal: 저점 스킵 |
| 2 | MCP↔MCP | `roles` 교집합 | official 우선 |
| 3 | Plugin↔Plugin | `roles`/`bundled` 교집합 | 저점 스킵 |
| 4 | Skill↔MCP 역할 중복 | `provides` 교집합 | 기록(Warning 표시 아님) |
| 5 | Plugin 내장 vs 외부 | `bundled` ∩ selected ids | 외부 쪽 스킵 |
| 6 | 동일 기능 중복 | `provides` 완전 포함 관계 | 포함되는 쪽 스킵 |
| 7 | 서로 다른 workflow 강제 | `workflow` 값이 둘 이상 | 1개만 유지 (Performance도 동일) |
| 8 | 동일 설정 파일 수정 | `config_targets` 동일 파일 + 동일 키 | 키 충돌 시 스킵, 파일만 같으면 merge |
| 9 | 동일 Tool 이름 | `tool_names` 교집합 | MCP 서버 alias 변경 또는 스킵 |
| 10 | Context 과다 | Σcontext_cost > 모드 한도 | Minimal: 저점부터 제거 / Performance: 경고 |
| 11 | 권한 충돌 | 기존 Agent 설정(sandbox/approval)과 컴포넌트 요구권한 불일치 | Plan Notes에 기록 |

선택/스킵 결정마다 이유 문자열을 남긴다(“추천 근거 항상 기록” 원칙).

---

## 7. 보안 검사 (`core/security.py`)

- **차단하지 않는다.** 결과는 `LOW` 또는 `WARNING` 뿐이며, WARNING이어도 일괄 승인 시 설치.
- 검사 대상: registry 메타데이터(permissions) + (가능 시) 고정 ref로 받은 소스의 정적 스캔. **실행은 하지 않음.**

| 대상 | 탐지 신호 (정규식/구조 기반) |
|---|---|
| Skill | prompt injection 문구(“ignore previous”, 숨김 지시), `rm -rf`, `curl … \| sh`, `~/.ssh`, `.aws/credentials`, `env` 덤프, 외부 다운로드, 파일 삭제/덮어쓰기, 과도한 `allowed-tools` |
| MCP | filesystem root 접근, network, 필수 credential, destructive tool 이름(delete/drop/force_push), shell/subprocess, repo write scope |
| Plugin | 내장 Skill/MCP 재귀 검사, install/update/postinstall script, 숨은 dependency, 권한 범위 |

- **업무별 가중치:** `registry/security_profiles.yaml`에서 domain → 중점 카테고리 매핑. 중점 카테고리에서 신호가 나오면 WARNING, 그 외 경미 신호는 LOW + 기록.
- `overall_risk = WARNING if any(WARNING) else LOW`.

---

## 8. Adapter 설계

```python
class AgentAdapter(ABC):
    kind: AgentKind
    def detect(self) -> AgentInstallation
    def inspect(self) -> list[InstalledComponent]
    def backup(self, dest: Path) -> BackupManifest
    def install_skill(self, c: Component, manifest) -> None
    def configure_mcp(self, c: Component, manifest) -> None
    def install_plugin(self, c: Component, manifest) -> None
    def health_check(self, plan: InstallPlan | None = None) -> HealthReport
    def rollback(self, manifest: BackupManifest) -> None
```

### 8.1 Codex (MVP 대상)
| 항목 | 설계 | 비고 |
|---|---|---|
| 홈 | `$CODEX_HOME` → 없으면 `~/.codex` | |
| 감지 | `which codex` + `codex --version`, config 디렉터리 존재 | 둘 중 하나만 있어도 “partial”로 표기 |
| 설정 | `config.toml` 의 `[mcp_servers.<name>]` | **tomlkit**로 주석/순서 보존 merge |
| Skill | `$CODEX_HOME/skills/<name>/SKILL.md` | 구현 착수 시 공식 문서로 경로 재확인 |
| Plugin | Codex 공식 plugin 체계 확인 전까지 `UnsupportedOperation` → Plan에서 제외 표기 | |
| Health | ① TOML parse ② SKILL.md frontmatter(name/description) 파싱 ③ 동일 name 중복 등록 없음 ④ (설치 후) MCP stdio 기동 + `initialize`/`tools/list` 응답 ⑤ `codex mcp list` 사용 가능 시 교차 확인 ⑥ env_keys 존재 여부로 인증 상태 표시 | 파일 존재 확인만으로 끝내지 않음 |

### 8.2 MCP 공유
- 동일 MCP 서버는 Agent별 설정에 **동일 command/args/env 참조**로 등록(프로세스 공유가 아닌 정의 공유). 원격(HTTP) MCP는 동일 URL 공유.

### 8.3 Merge 정책
- 기존 키가 동일 값 → no-op, 다른 값 → **덮어쓰지 않고** 충돌로 기록·스킵(규칙 8).
- 모든 쓰기는 temp 파일 → parse 검증 → atomic rename.

---

## 9. 백업 / Rollback

```
~/.grayom/
├── backups/<YYYYmmdd-HHMMSS>/
│   ├── manifest.json        # BackupManifest
│   └── codex/config.toml    # 원본 사본 (권한 0600)
└── cache/                   # 컴포넌트 메타데이터 캐시 (사용자 프로필 아님)
```
- installer는 action 수행 **직전** manifest에 `created_paths`/`applied_actions`를 append → 중간 실패에도 부분 설치 추적 가능.
- rollback: 원본 파일 복원(sha256 검증) → created_paths 삭제(GrayOM이 만든 경로만, 경로가 Agent 홈 하위인지 검증) → 결과 보고.
- `grayom rollback` : 가장 최근(또는 `--id`) manifest 기준 수동 복원.

---

## 10. 요구사항 충돌·모호점 (결정 필요)

임의 결정하지 않고, 아래는 **제안안**만 표기. 승인 전까지 확정 아님.

| ID | 충돌/모호 내용 | 제안 |
|---|---|---|
| **C-1** | 설치 흐름상 “2. 백업”이 인터뷰 전인데, 원칙은 “최종 승인 전 Agent 설정 수정 금지”. 백업은 Agent 설정을 수정하진 않지만 `~/.grayom`에 파일을 쓴다. 취소 시에도 백업이 남음 | 백업을 **승인 직후, 설치 직전**으로 이동. 승인 전 단계는 완전 read-only |
| **C-2** | “사용자 프로필 저장 제외” vs `grayom rollback`/캐시는 로컬 저장 필요 | 백업 manifest·컴포넌트 캐시만 저장, 인터뷰 응답(업무/Agent 선택)은 **저장 안 함**. 단 manifest에 설치 대상 Agent 목록은 포함(복원에 필수) |
| **C-3** | “실행할 때마다 최신 후보 재확인” vs MVP 우선순위 10번(실시간 탐색은 마지막) | MVP는 로컬 registry + 캐시만 사용. `sources/github.py`는 인터페이스만 두고 미구현. Plan에 “Source: local registry (online check disabled)” 표시 |
| **C-4** | 제시된 구조는 `cli/`, `core/`, `models/` 등이 top-level 패키지 → 설치 시 site-packages에 `core`, `models` 같은 범용 이름이 충돌 | `src/grayom/{cli,core,adapters,sources,models,registry}` 로 **네임스페이스만 추가**, 내부 구조는 요구안 그대로 |
| **C-5** | 기술 스택에 TOML 쓰기 라이브러리 없음. Codex `config.toml`을 주석 보존 merge하려면 필요 | `tomlkit` 의존성 추가 (읽기는 표준 `tomllib`) |
| **C-6** | 같은 컴포넌트가 Agent마다 형태가 다름 (예: Superpowers = Claude Code에선 Plugin, Codex에선 Skill) | `Component.install`을 Agent별 스펙 맵으로 두고, Plan에는 Agent별 설치 형태를 표기 |
| **C-7** | Codex Plugin 지원 여부/형식 불확실 | MVP에서 Codex `install_plugin`은 Unsupported 처리, Plan에 “Codex: plugin not supported → skipped” |
| **C-8** | “Rich + InquirerPy” 조합에서 InquirerPy는 비대화형(CI/파이프) 환경에서 동작 불가 | TTY 없으면 인터뷰 대신 `--agents/--domains/--tasks/--mode` 옵션 입력 요구 (테스트에도 활용). 기능 추가가 아니라 테스트 가능성 확보 목적 |
| **C-9** | `grayom`(인자 없음)의 동작 미정의 | 로고 + `setup`과 동일 동작 |
| **C-10** | Health Check의 MCP 기동은 외부 코드 실행 → 승인 후에만 수행 | 승인 전 `doctor`는 파싱/중복 검사만, MCP 기동 검사는 `--deep` 플래그 또는 설치 직후에만 |

---

## 11. MVP 범위

### In (이번 1차 작업: 골격)
1. `architecture.md` (본 문서)
2. 디렉터리 구조 + `pyproject.toml` (Typer/Rich/InquirerPy/Pydantic/httpx/PyYAML/tomlkit, pytest)
3. Pydantic 모델 전체 정의 (`models/`)
4. CLI: ASCII 로고, `setup`/`recommend`의 **인터뷰 화면까지** (Agent → Domain → 도메인별 세부작업 → Mode), 비TTY 옵션 입력
5. Codex Adapter: `detect()`, `backup()`, `health_check()`(config parse / skill frontmatter / 중복 등록 검사). 나머지 메서드는 `NotImplementedError`
6. 테스트: 모델 검증, 인터뷰 결과 매핑(프롬프트 mock), Codex detect/backup/health (tmp `CODEX_HOME` 사용), CLI 스모크

### 2차 (Codex end-to-end 완성)
registry YAML 샘플 → capability_inference → recommender → conflict → security → Plan 렌더 → 승인 → Codex install_skill/configure_mcp → deep health → rollback

### 3차 이후
Claude Code Adapter → Cursor Adapter → official/GitHub 실시간 탐색 + 캐시

### Out (명시 제외)
Agent 설치, 개발환경 구성, Gemini CLI, Web UI, 사용자 프로필 저장, 위험 등급 3단계 이상, WARNING 기반 설치 차단

---

## 12. 1차 작업 파일 변경 계획

```
Agent_Guidance/
├── architecture.md                     (신규) 본 문서
├── README.md                           (수정) 개요/설치/사용법 최소 기재
├── pyproject.toml                      (신규) entry point: grayom = grayom.cli.main:app
├── src/grayom/
│   ├── __init__.py                     버전
│   ├── paths.py                        ~/.grayom, CODEX_HOME 경로 해석
│   ├── cli/
│   │   ├── main.py                     Typer app, setup/recommend/doctor/rollback (doctor/rollback은 Codex health·안내만)
│   │   ├── interview.py                InquirerPy 인터뷰 + 옵션 입력 → InterviewResult
│   │   ├── catalog.py                  Domain/Task 선택지 정의 (도메인→세부작업 매핑)
│   │   └── ui.py                       로고, 감지 결과, 인터뷰 요약 렌더
│   ├── core/__init__.py                (2차에서 모듈 추가, 빈 패키지)
│   ├── adapters/
│   │   ├── base.py                     AgentAdapter ABC
│   │   └── codex.py                    detect / backup / health_check
│   ├── sources/__init__.py             (2차)
│   ├── models/
│   │   ├── agent.py                    AgentKind, AgentInstallation, InstalledComponent
│   │   ├── component.py                ComponentType, Component, InstallSpec, Permission
│   │   ├── interview.py                Domain, Task, Mode, InterviewResult
│   │   ├── recommendation.py           Capability, Selection, ConflictFinding, InstallPlan, PlannedAction
│   │   ├── risk.py                     RiskLevel, RiskFinding
│   │   └── backup.py                   BackupManifest, HealthCheck, HealthReport
│   └── registry/                       (2차에 known_*.yaml)
└── tests/
    ├── test_models.py
    ├── test_interview.py
    ├── test_codex_adapter.py
    └── test_cli.py
```
