# Step 10 실행 산출물

## 목적
성과 필터/랭킹/상관중복 제거 규칙을 Evaluator로 구현한다.

## 완료 범위
- 기본 통과 필터:
  - `src/brain_agent/evaluation/evaluator.py` (`Evaluator._failure_reasons`)
  - 정책 분리: `configs/filter_policy.json`, `src/brain_agent/config.py`
- 안정성 점검:
  - `Evaluator.stability_from_yearly_stats`
- 상관/중복 제거:
  - `Evaluator.select_low_correlation` (|corr| threshold 적용)
- 실행 스크립트:
  - `scripts/evaluate_results.sh`

## Step 11+ 인계 메모
- Step 11 피드백 에이전트는 ScoreCard의 실패 사유를 직접 입력으로 사용한다.
