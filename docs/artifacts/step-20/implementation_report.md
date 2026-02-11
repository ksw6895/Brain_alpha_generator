# Step 20 Implementation Report

기준일: 2026-02-12

## 1) 코드 변경 파일
- `configs/llm_budget.json`
- `src/brain_agent/generation/budget.py`
- `src/brain_agent/agents/llm_orchestrator.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/server/app.py`
- `src/brain_agent/storage/sqlite_store.py`
- `src/brain_agent/generation/__init__.py`
- `README.md`
- `docs/steps/README.md`
- `docs/steps/step-20.md`
- `docs/artifacts/step-20/implementation_report.md`

## 2) 반영 범위 요약
1. budget config 도입
- 요청/배치/일일 예산, fallback 단계, exploit/explore 비율, explore floor, expansion reserve를 `configs/llm_budget.json`으로 고정.

2. step-20 budget 레이어 구현
- `generation/budget.py`에 rough token estimator, usage 집계, budget 평가, staged fallback(필드→연산자→서브카테고리), coverage/novelty KPI 계산 추가.
- `BudgetBlockedError`로 budget 차단을 명시적 실패로 처리.

3. 오케스트레이터 연동
- `run-alpha-maker` 호출 전에 budget gate를 강제.
- `budget.fallback_applied`, `budget.check_passed`, `budget.check_failed`, `budget.explore_floor_preserved`, `budget.blocked` 이벤트를 저장.
- `llm.usage_point`에 `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`를 추가.

4. 대시보드 API 계약 추가
- `GET /api/runs/{run_id}/budget`
- `GET /api/runs/{run_id}/kpi`
- 응답을 `series`, `gauges`, `flags` 형식으로 고정.

5. CLI 검증 경로 추가
- `estimate-prompt-cost` 명령 도입.
- retrieval pack + knowledge pack 기준으로 budget 평가/폴백 결과를 JSON으로 출력.

## 3) 실행/검증 커맨드와 결과

### 3.1 retrieval pack 생성
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/retrieval_pack_step20.json
```
결과 요약:
- 성공
- candidate counts: `subcategories=5`, `datasets=15`, `fields=72`, `operators=60`

### 3.2 budget pass 케이스 (fallback 적용 후 통과)
```bash
PYTHONPATH=src python3 -m brain_agent.cli estimate-prompt-cost \
  --retrieval-pack /tmp/retrieval_pack_step20.json \
  --knowledge-pack-dir data/meta/index \
  --llm-budget-config configs/llm_budget.json \
  --output /tmp/budget_estimate_step20_pass.json
```
결과 요약:
- 종료코드 `0`
- `ok=true`
- `fallback_count=7`
- 최종 `prompt_tokens_rough=9122`
- 최종 top-k: `fields=9`, `operators=19`, `subcategories=4`

### 3.3 budget blocked 케이스 (강한 제한)
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
결과 요약:
- 종료코드 `2`
- stderr: `{"error":"budget_blocked","message":"alpha generation blocked by budget policy: request_prompt"}`
- `budget.check_failed`, `budget.blocked` 이벤트 기록 확인

### 3.4 telemetry 이벤트 확인 (run_id=step20-run)
결과 요약:
- 이벤트 순서: `agent.alpha_started` → `budget.fallback_applied`(7회) → `budget.check_passed` → `budget.explore_floor_preserved` → `agent.alpha_generated` → `llm.usage_point`
- `budget.*` payload에 `selected_topk`, `fallback_count`, `coverage_kpi`, `novelty_kpi` 포함

### 3.5 API 페이로드 스키마 확인
- FastAPI 런타임 의존성(`fastapi`)이 현재 테스트 환경에 미설치라 HTTP 서버 실기동 검증은 미수행.
- 대신 동일 빌더 함수(`build_budget_console_payload`, `build_kpi_payload`)로 `series/gauges/flags` 구조 생성 확인.

## 4) 실패 케이스와 재현 방법

### 4.1 일일 예산 초과
재현:
1. `max_tokens_per_day`를 낮게 설정
2. 당일 `llm.usage_point` 누적치가 상한을 넘는 상태에서 `run-alpha-maker` 실행

예상:
- `budget.check_failed` + `budget.blocked`
- CLI는 `budget_blocked` 오류로 종료

대응:
1. `configs/llm_budget.json`의 `max_tokens_per_day` 상향
2. run batch 크기/재시도 횟수 축소

### 4.2 지식팩 파일 누락
재현:
1. `data/meta/index` 필수 파일 삭제
2. `estimate-prompt-cost` 또는 `run-alpha-maker` 실행

예상:
- knowledge pack 로드 오류로 실패

대응:
1. `build-knowledge-pack` 재실행
2. 경로/권한 확인

## 5) 다음 step 진입 조건
1. step-21에서 validation-first repair loop가 호출될 때, `budget.blocked`/`budget.check_passed` 이벤트를 입력 조건으로 사용 가능.
2. 반복 validation 오류 시 `expansion_reserve_tokens`를 소비하는 확장 분기 연결만 추가하면 step-20/21 계약이 자연스럽게 이어짐.
