# Step 13 실행 산출물

## 목적
다양성 endpoint 기반으로 region/delay/dataCategory 편중을 계량화한다.

## 완료 범위
- diversity endpoint 래퍼:
  - `src/brain_agent/brain_api/diversity.py` (`get_diversity`)
- 다양성 점수 계산:
  - `src/brain_agent/evaluation/diversity.py`
    - `diversity_bonus`
    - `blended_final_score`
- 정책 템플릿:
  - `configs/diversity_policy.json`
- 실행 스크립트:
  - `scripts/diversity_snapshot.sh`

## Step 14+ 인계 메모
- Step 14 Done Definition 검증 시 diversity 보너스 반영 여부를 포함한다.
