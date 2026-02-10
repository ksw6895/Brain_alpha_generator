# Step 9 실행 산출물

## 목적
시뮬레이션 제출/폴링/결과수집 자동화와 중복 제출 방지 로직을 구현한다.

## 완료 범위
- 기본 시뮬 요청/폴링:
  - `src/brain_agent/brain_api/simulations.py`
    - `start_simulation`, `poll_simulation`, `run_single_simulation`
  - `Retry-After` 헤더 준수 구현
- 멀티 시뮬(2~10):
  - `run_multi_simulation`
  - `SimulationRunner.run_candidates_multi`
- 중복 시뮬 방지:
  - fingerprint 계산: `src/brain_agent/utils/fingerprints.py`
  - normalized expression: `src/brain_agent/utils/expressions.py`
  - 저장/중복체크: `simulation_fingerprints` 테이블 (`src/brain_agent/storage/sqlite_store.py`)
- recordsets 수집:
  - `get_alpha_recordsets`, `get_recordset`
  - `SimulationRunner._fetch_and_save_recordsets`
  - 실행 스크립트: `scripts/simulate_candidates.sh`

## Step 10+ 인계 메모
- 평가기 입력은 본 단계 결과(`alpha_results`, recordsets 저장물) 기준으로 구성한다.
