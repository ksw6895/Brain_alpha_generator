# Step 21 Implementation Report

기준일: 2026-02-12

## 1) 상태 요약
- step-21 validation-first gate + repair loop + queue 정책 + 시뮬/평가 이벤트 계약 구현 완료.
- `run-validation-loop` CLI가 생성 -> 검증 -> 수정 -> 재검증 -> (통과 시) 시뮬 -> 평가 경로를 강제한다.
- Arena/Evolutionary Tree 이벤트 계약(`simulation.*`, `evaluation.completed`, `mutation.child_created`)이 DB/WS에서 조회 가능하다.

## 2) 코드 변경 파일
- `src/brain_agent/generation/validation_gate.py` (신규)
- `src/brain_agent/agents/validation_loop.py` (신규)
- `src/brain_agent/simulation/runner.py`
- `src/brain_agent/brain_api/simulations.py`
- `src/brain_agent/evaluation/evaluator.py`
- `src/brain_agent/feedback/mutator.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/schemas.py`
- `src/brain_agent/agents/pipeline.py`
- `src/brain_agent/agents/__init__.py`
- `src/brain_agent/generation/__init__.py`
- `src/brain_agent/server/app.py`
- `docs/artifacts/step-21/neural_genesis_lab.html` (신규)
- `README.md`
- `docs/steps/README.md`
- `docs/steps/step-21.md`
- `architecture/current-workflow-map.md`
- `docs/artifacts/step-21/implementation_report.md` (신규)

## 3) 반영 범위 요약
1. validation-first gate
- `ValidationGate` 추가:
  - 정적검증 실행
  - taxonomy 기반 오류 코드 분류
  - repair instruction payload 생성
  - deterministic repair(unknown operator/field, scope/type/arity/괄호 오류 보정)

2. repair loop 오케스트레이터
- `ValidationLoopOrchestrator` 추가:
  - `max_repair_attempts`, `stop_on_repeated_error` 지원
  - 반복 동일 오류에서 retrieval expansion branch 실행
  - `event_order_violation` 검사 + `run.summary` 기록

3. queue 정책 강제
- `GenerationNotes`에 `validation_passed`, `validation_attempts` 추가
- `SimulationRunner(enforce_validation_gate=True)`에서 `validation_passed != true` 후보 차단
- queue 메타에 `candidate_lane`, `validation_*` 보존

4. 시뮬/평가/변이 이벤트 계약
- `simulation.enqueued`, `simulation.started`, `simulation.completed` 추가
- legacy alias `simulation_completed` 병행 유지
- `poll_simulation()` progress callback 훅 추가 + `simulation.progress` 이벤트
- `Evaluator.evaluate(..., run_id=...)`에서 `evaluation.completed` 저장
- `FeedbackMutator`에서 `mutation.child_created`(parent-child lineage) 이벤트 저장

5. CLI 엔트리포인트
- `run-validation-loop` 신규:
  - 내부에서 `run-alpha-maker` 생성 단계 호출
  - validation-first 루프 실행
  - 통과 후보만 출력 JSON에 저장
  - 요약 리포트(`--report-output`) 지원

6. validation KPI 조회 API
- `GET /api/runs/{run_id}/validation_kpi`
  - attempt별 `passed/failed/pass_rate`
  - run summary(`final_passed/final_failed/retrieval_expanded`) 조회

7. F21 프로토타입
- `docs/artifacts/step-21/neural_genesis_lab.html`
  - Data Synapse Map / Evolutionary Galaxy / Arena Spectator / Terminal
  - `/ws/live` 구독으로 실시간 이벤트 반영
- 서버 경로 추가: `GET /ui/neural-lab`

## 4) 검증 커맨드와 결과

### 4.1 정적 컴파일 점검
```bash
PYTHONPATH=src python3 -m compileall -q src
```
결과:
- 성공

### 4.2 CLI 등록 확인
```bash
PYTHONPATH=src python3 -m brain_agent.cli --help
PYTHONPATH=src python3 -m brain_agent.cli run-validation-loop --help
```
결과:
- `run-validation-loop` 서브커맨드 노출 확인

### 4.3 dry-run (skip simulation)
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/retrieval_pack_step21.json

PYTHONPATH=src python3 -m brain_agent.cli run-validation-loop \
  --llm-provider mock \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --retrieval-pack /tmp/retrieval_pack_step21.json \
  --knowledge-pack-dir data/meta/index \
  --skip-simulation \
  --run-id step21-dryrun \
  --output /tmp/validated_candidates_step21.json \
  --report-output /tmp/step21_dryrun_report.json
```
결과:
- `validation_passed=true`
- `event_order_violation=false`
- run 이벤트 순서 확인:
  - `agent.alpha_generated -> validation.started -> validation.passed -> evaluation.completed`

### 4.4 repair retry 통과 프로브 (CLI)
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-validation-loop \
  --llm-provider mock \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --retrieval-pack /tmp/retrieval_pack_step21.json \
  --knowledge-pack-dir data/meta/index \
  --raw-output /tmp/step21_bad_candidate_raw.json \
  --skip-simulation \
  --run-id step21-repair-probe \
  --max-repair-attempts 3 \
  --output /tmp/validated_candidates_step21_repair.json \
  --report-output /tmp/step21_repair_report.json
```
결과:
- `validation_passed=true`
- `validation_attempts=2`
- 핵심 이벤트:
  - `validation.failed -> validation.retry_started -> validation.retry_passed`
  - `evaluation.completed`

### 4.5 validation KPI 조회 프로브
```bash
PYTHONPATH=src python3 - <<'PY'
from brain_agent.storage.sqlite_store import MetadataStore

store = MetadataStore("data/brain_agent.db")
rows = store.list_event_records_for_run(run_id="step21-repair-probe", limit=200)
events = [row["payload"] for row in rows]
attempts = {}
for event in events:
    et = str(event.get("event_type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    attempt = int(payload.get("attempt") or 0)
    attempts.setdefault(attempt, {"passed": 0, "failed": 0})
    if et in {"validation.passed", "validation.retry_passed"}:
        attempts[attempt]["passed"] += 1
    if et in {"validation.failed", "validation.retry_failed"}:
        attempts[attempt]["failed"] += 1
print(attempts)
PY
```
결과:
- attempt별 pass/fail 집계 가능한 이벤트가 저장됨
- `GET /api/runs/{run_id}/validation_kpi`는 FastAPI 런타임 의존성 설치 환경에서 조회 가능

### 4.6 반복 오류 + retrieval 확장 분기 프로브
실행 방법:
- `StaticValidator(operators=[], fields=[])`를 사용한 로컬 프로브 스크립트로 의도적으로 동일 오류를 반복시킴
- run id: `step21-repeated-error-probe`

결과:
- `validation_passed=false`
- `validation_attempts=4`
- `retrieval_expanded=true`
- `event_order_violation=false`
- 핵심 이벤트:
  - `validation.failed`
  - `validation.retry_failed` 반복
  - `validation.retrieval_expanded` 발생 확인
  - `simulation.blocked_validation`
  - `evaluation.completed`

### 4.7 시뮬/평가 이벤트 순서 프로브(로컬 모의)
실행 방법:
- `brain_agent.simulation.runner.run_single_simulation`를 로컬 fake 함수로 monkeypatch
- run id: `step21-sim-probe`

결과:
- `validation_passed=true`
- `simulated=1`, `evaluated=1`
- `event_order_violation=false`
- 핵심 이벤트 순서:
  - `agent.alpha_generated`
  - `validation.started -> validation.passed`
  - `simulation.enqueued -> simulation.started -> simulation.progress -> simulation.completed`
  - `evaluation.completed`

## 5) 실패 케이스와 대응
1. CLI 실행 시 `UnboundLocalError: EventBus`
- 원인: `main()` 내부 로컬 import가 변수 스코프를 가림
- 대응: `serve-live-events` 분기에서 로컬 import 제거

2. pandas 미설치 환경에서 evaluator import 실패
- 원인: `Evaluator` 모듈 import 시 `pandas` 강제
- 대응: evaluator를 pandas optional 모드로 보강
  - 기본 점수 계산 경로는 pandas 없이 동작
  - 상관/연도통계 기능은 호출 시 명시적 오류 반환

## 6) step-21 인계 요약
- validation-first 기본 경로, 반복 오류 확장 분기, queue gating, simulation/evaluation/mutation 이벤트 계약이 코드에 반영됨.
- 이후 권장 작업:
  1. 제출 우선순위에 diversity score 결합
  2. 운영 대시보드(비용/통과율/중복률) 자동화
