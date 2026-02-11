# Step 20 Implementation Report

기준일: 2026-02-12

## 0) 상태 요약 (최종)
- step-20 백엔드(예산 강제, staged fallback, telemetry, `budget/kpi/reactor_status` API) 완료.
- step-20 프론트(HUD 프로토타입: 3D 토큰 코어 + Cost Pulse + Exploit/Explore Radar + 60fps 보간) 완료.
- 실제 백테스트 응답 이벤트(`simulation_completed`)를 확보했고, 그 결과를 반영해 `reactor_status` 필드를 보정했다.

## 1) 코드 변경 파일
- `configs/llm_budget.json`
- `src/brain_agent/generation/budget.py`
- `src/brain_agent/generation/__init__.py`
- `src/brain_agent/agents/llm_orchestrator.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/server/app.py`
- `src/brain_agent/storage/sqlite_store.py`
- `src/brain_agent/simulation/runner.py`
- `src/brain_agent/brain_api/simulations.py`
- `docs/artifacts/step-20/reactor_hud.html`
- `README.md`
- `docs/steps/README.md`
- `docs/steps/step-20.md`
- `docs/steps/step-21.md`
- `docs/artifacts/step-20/implementation_report.md`

## 2) 반영 범위 요약
1. budget config/정책 고정
- `configs/llm_budget.json` 기반으로 요청/배치/일일 예산, exploit/explore, fallback step, expansion reserve 강제.

2. budget gate + staged fallback
- `enforce_alpha_prompt_budget()`에서 `fields -> operators -> subcategories` 순서로 축소.
- 실패 시 `BudgetBlockedError`로 명시적 차단.

3. telemetry 이벤트 계약
- `budget.fallback_applied`, `budget.check_passed`, `budget.check_failed`, `budget.explore_floor_preserved`, `budget.blocked`
- `llm.usage_point`에 token/cost 포인트를 누적.

4. step-20 대시보드 API
- `GET /api/runs/{run_id}/budget`
- `GET /api/runs/{run_id}/kpi`
- `GET /api/runs/{run_id}/reactor_status` (신규)

5. Reactor HUD 데이터 계약(신규)
- `build_reactor_status_payload()` 추가:
  - `series`: `cost_pulse`, `pressure`, `coverage`, `novelty`, `explore_ratio`, `fallback_timeline`
  - `gauges`: token gauges + `pressure` + `velocity_tokens_per_sec` + `velocity_cost_usd_per_min`
  - `flags`: budget/over-limit + `protection_mode` + `reactor_state`
  - `reactor`: `core`, `token_gauge`, `cost_pulse`, `exploit_explore_radar`, `fallback`, `render_hints`

6. WS 실시간 연동 확장
- `/ws/live`에 `include_reactor=1`, `reactor_interval_sec`, `run_id` 필터 추가.
- `reactor.status` 스냅샷 이벤트를 주기 전송.

7. HUD 프로토타입(로컬 정적 UI)
- `docs/artifacts/step-20/reactor_hud.html`
- 3D 코어(Three.js), Cost Pulse 캔버스, Radar 캔버스, 보호모드 오버레이, 60fps 보간 렌더.
- 서버 경로: `GET /ui/reactor`

8. 실백테스트 후속 안정화
- 실측 실행 중 발견된 API 편차를 반영:
  - `simulation payload`에서 null optional 필드 제거(`selection/combo/regular`).
  - recordsets endpoint가 non-JSON이어도 시뮬 결과 저장이 끊기지 않도록 non-fatal 처리.

## 3) 실측 백테스트 데이터 (actual)
실행 컨텍스트:
- 명령: `simulate-candidates --interactive-login --input data/probes/step20/candidates_probe.json`
- biometrics 인증 후 실제 제출/완료 확인

실측 이벤트(1차):
- `event_type`: `simulation_completed`
- `alpha_id`: `j2l8Vzv9`
- `created_at`: `2026-02-11T16:22:51.127439+00:00`
- metrics:
  - `sharpe=-0.64`
  - `fitness=-0.35`
  - `turnover=0.1913`
  - `drawdown=0.6091`
  - `coverage=null`

실측 결과 파일(2차 rerun, 저장 성공):
- 파일: `data/probes/step20/alpha_result_probe_rerun.json`
- `alpha_id`: `O0w8RPJd`
- `created_at`: `2026-02-11T16:35:10.180880+00:00`
- summary metrics:
  - `sharpe=-0.63`
  - `fitness=-0.35`
  - `turnover=0.1856`
  - `drawdown=0.6017`
  - `coverage=null`
- payload 구조 확인:
  - `raw_payload.is` + `raw_payload.train` + `raw_payload.test`
  - `raw_payload.is.checks[*]` (`PASS|FAIL|WARNING|PENDING`)

실측 기반 설계 보정:
1. `coverage`는 null 가능 -> KPI/gauge null-safe 처리 필요.
2. recordsets endpoint는 계정/권한에 따라 non-JSON 가능 -> Arena 1차 UI는 `simulation_completed.metrics`만으로도 동작해야 함.
3. progress field가 항상 보장되지 않으므로 "실시간 상세 PnL 중계"는 선택 기능으로 분리.
4. step-21 초기 맵핑은 `is` 블록을 기준으로 하고, `train/test/checks`는 확장 정보로 비동기 렌더링하는 것이 안정적.

## 4) 검증 커맨드와 결과

### 4.1 budget pass 케이스
```bash
PYTHONPATH=src python3 -m brain_agent.cli estimate-prompt-cost \
  --retrieval-pack /tmp/retrieval_pack_step20.json \
  --knowledge-pack-dir data/meta/index \
  --llm-budget-config configs/llm_budget.json \
  --output /tmp/budget_estimate_step20_pass.json
```
결과:
- `ok=true`
- fallback 적용 후 통과

### 4.2 budget blocked 케이스
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-alpha-maker \
  --llm-provider mock \
  --llm-budget-config /tmp/llm_budget_tight.json \
  --run-id step20-block \
  --idea /tmp/idea_step20_run.json \
  --retrieval-pack /tmp/retrieval_pack_step20_run.json \
  --knowledge-pack-dir data/meta/index \
  --output /tmp/candidate_alpha_step20_block.json
```
결과:
- 종료코드 `2`
- `budget_blocked` 반환 확인

### 4.3 reactor payload 빌더 검증
```bash
PYTHONPATH=src python3 - <<'PY'
from brain_agent.storage.sqlite_store import MetadataStore
from brain_agent.generation.budget import load_llm_budget, build_reactor_status_payload
store = MetadataStore("data/brain_agent.db")
run_id = "step20-run-2"
run_events = [r["payload"] for r in store.list_event_records_for_run(run_id=run_id, limit=2000)]
all_events = [r["payload"] for r in store.list_event_records(limit=5000)]
payload = build_reactor_status_payload(
    run_id=run_id,
    run_events=run_events,
    all_events=all_events,
    budget=load_llm_budget("configs/llm_budget.json"),
)
print(sorted(payload.keys()))
PY
```
결과:
- `['as_of', 'flags', 'gauges', 'reactor', 'run_id', 'series']` 구조 확인

## 5) 실패 케이스와 대응

### 5.1 `POST /simulations` 400 null 필드 오류
증상:
- `combo` / `selection` null 금지 에러

원인:
- payload에 optional null field가 그대로 포함됨

대응:
- `SimulationRunner`에서 `exclude_none=True` + optional expression key 정리

### 5.2 recordsets JSONDecodeError
증상:
- `/alphas/{id}/recordsets` 2xx 응답이 non-JSON일 때 예외 발생

원인:
- 응답 본문 JSON 가정

대응:
- `get_alpha_recordsets()` JSON 파싱 실패 시 빈 리스트 반환
- recordset fetch 실패는 non-fatal 이벤트(`simulation.recordsets_unavailable`)로 다운그레이드

## 6) 다음 step 진입 조건
1. step-21에서 validation-first gate/repair loop를 붙일 때 step-20 budget 이벤트를 입력 상태로 그대로 활용 가능.
2. Arena 실시간성은 2계층으로 구현:
   - 필수: `simulation.*` 단계 이벤트
   - 선택: recordset 기반 상세 스트림(가능 계정만)
