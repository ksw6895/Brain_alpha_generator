# Step 20

## 토큰/비용 제어 레이어 구축

## 0) 이 문서만 읽은 신규 에이전트용 요약
- step-19까지 오면 LLM 호출 체인은 동작할 수 있다.
- 하지만 비용 제어가 없으면 "동작하지만 운영 불가능" 상태가 된다.
- step-20은 호출 예산, 자동 축소, 캐시를 통해 비용을 상한선 안으로 고정한다.
- 단, 비용 최적화가 탐색을 죽이지 않도록 exploit/explore 예산을 분리한다.
- 이 step에서 "Budget/Quality 대시보드" telemetry 계약도 함께 고정한다.

## 1) 배경과 의도
### 1.1 문제
- 아이디어 품질이 낮을수록 재시도가 늘고 비용이 급증한다.
- retrieval pack이 커지면 prompt 토큰이 빠르게 증가한다.

### 1.2 목표
- 요청 단위 비용과 배치 단위 비용을 모두 통제한다.
- 예산 초과 시 자동으로 Top-K를 줄이는 폴백을 제공한다.

## 2) 정책 범위
### 2.1 예산 계층
1. 요청당 예산
- input tokens
- output tokens

2. 배치당 예산
- 아이디어 N개에 대한 총 토큰

3. 기간당 예산
- 일/주 단위 토큰 또는 비용 상한

4. 탐색 전용 예산
- explore lane 최소 비율(권장 20~30%)을 별도로 보장

### 2.2 권장 시작값
- prompt budget: 8k~16k
- completion budget: 1k~2k
- batch hard cap: 팀 상황에 맞게 설정 (문서화 필수)
- exploit/explore ratio: 70/30 (초기값)

### 2.3 프론트 동시 적용 범위 (F20: Budget Console)
- 목적: 사용자가 현재 run의 비용 상태와 fallback 동작을 실시간 계기판으로 확인
- 필수 시각화:
  1. prompt/completion 토큰 게이지
  2. fallback 단계 타임라인
  3. coverage/novelty KPI 트렌드
  4. explore lane 보존율(최소치 미만 여부)

## 3) 구현 범위
### 3.1 설정
- 신규: `configs/llm_budget.json`
- 필드 예시:
  - `max_prompt_tokens`
  - `max_completion_tokens`
  - `max_tokens_per_batch`
  - `max_tokens_per_day`
  - `fallback_topk_steps`
  - `exploit_ratio`
  - `explore_ratio`
  - `min_explore_candidates_per_batch`
  - `expansion_reserve_tokens`

### 3.2 코드
- 신규(권장): `src/brain_agent/generation/budget.py`
- 기능:
  1. rough token estimator
  2. 예산 검사기
  3. 초과 시 Top-K 자동 축소
  4. 호출 로그 적재

### 3.3 로그
- `event_log` 또는 별도 JSONL에 최소 항목 저장:
  - step name
  - prompt/completion tokens
  - selected Top-K
  - exploit/explore lane 비율
  - 예산 초과 여부
  - fallback 횟수
  - coverage KPI (subcategory unique count)
  - novelty KPI (신규 operator/field 조합 비율)
- 이벤트명 권장:
  - `budget.check_passed`
  - `budget.check_failed`
  - `budget.fallback_applied`
  - `budget.explore_floor_preserved`
  - `budget.blocked`

### 3.4 대시보드 조회용 API 계약
- 신규(권장): `src/brain_agent/server/app.py` REST endpoint
  - `GET /api/runs/{run_id}/budget`
  - `GET /api/runs/{run_id}/kpi`
- 소비자(권장): `frontend-next/`의 Tremor/Recharts 대시보드 컴포넌트
- 응답은 차트 친화 포맷으로 제공
  - `series`: 시계열 배열
  - `gauges`: 현재값/한도값
  - `flags`: 경고 상태

### 3.5 코드 연결 포인트 (현재 구현 기준)
1. `src/brain_agent/storage/sqlite_store.py`
- 기존 `append_event()`를 그대로 재사용해 budget telemetry를 저장한다.
2. `src/brain_agent/agents/pipeline.py`
- 현재 `metadata_sync`, `cycle_completed` 이벤트가 저장되므로 run 경계(run_id) 주입 지점으로 사용한다.
3. `src/brain_agent/simulation/runner.py`
- simulation 결과 이벤트와 budget 이벤트를 같은 run_id로 연결해 Arena/Budget 교차 조회를 가능하게 한다.

## 4) fallback 순서 (강제)
예산 초과 시 아래 순서대로 축소:
1. fields Top-K 축소
2. operators Top-K 축소
3. subcategory 수 축소
4. 그래도 초과면 아이디어 이월/폐기
5. 단, explore lane 최소치(`min_explore_candidates_per_batch`)는 유지

## 4.1 반복 오류 확장 예산
1. 동일 validation 오류가 반복되면 축소 정책을 일시 중단
2. `expansion_reserve_tokens` 범위 내에서 Top-K 확장을 허용
3. 확장 후에도 실패하면 step-21 repair loop로 위임

## 5) 검증 커맨드 (완료 기준)
예시:
```bash
PYTHONPATH=src python3 -m brain_agent.cli estimate-prompt-cost \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index
```

검증 항목:
1. 예산 미초과 요청은 그대로 통과
2. 예산 초과 요청은 fallback이 단계적으로 동작
3. fallback 후에도 초과면 실패 코드가 명확히 반환
4. 로그가 남는다
5. explore lane 최소 비율이 유지된다
6. coverage/novelty KPI가 저장된다
7. WebSocket 또는 REST 조회로 Budget Console UI가 실시간 갱신된다

## 6) 완료 정의 (Definition of Done)
- [x] budget config 파일 도입
- [x] 예산 검사 + fallback 로직 구현
- [x] 호출 토큰/비용 로그 저장
- [x] 배치 단위 상한 적용
- [x] exploit/explore 이중 예산이 강제됨
- [x] 리서치 품질 KPI(coverage/novelty)가 수집됨
- [x] 대시보드용 telemetry 이벤트 계약이 고정됨
- [x] run 단위 budget/kpi 조회 API가 정의됨

## 7) 다음 step 인계
- step-21은 budget 레이어를 통과한 생성 결과만 받아 validation-first loop를 완성한다.
