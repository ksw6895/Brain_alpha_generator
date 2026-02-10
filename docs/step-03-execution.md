# Step 3 실행 산출물

## 목적
`OPTIONS /simulations`를 하드코딩 없이 동기화하고 settings 사전검증 기반을 마련한다.

## 완료 범위
- OPTIONS 수집/파싱:
  - `src/brain_agent/brain_api/metadata.py` (`get_simulation_options`, `parse_simulation_allowed_values`)
- 로컬 저장:
  - `src/brain_agent/metadata/sync.py` (`sync_simulation_options`)
  - `data/meta/simulations_options.json`
  - `data/meta/simulations_options_<date>.json`
- 활용(검증기):
  - `src/brain_agent/validation/settings_validator.py`
  - 타겟 기본값: `configs/target.default.json`
  - 실행 스크립트: `scripts/sync_options.sh`

## Step 4+ 인계 메모
- Step 4 메타데이터 수집 시 `configs/target.default.json` 조합(EQUITY/USA/TOP3000/delay=1)을 기본 시작점으로 사용한다.
