# Step 11 실행 산출물

## 목적
평가 결과를 바탕으로 자동 파라미터 탐색/표현식 변형 루프를 구현한다.

## 완료 범위
- 실패 원인 분류 템플릿:
  - `src/brain_agent/feedback/mutator.py` (`classify_failure`)
- 파라미터 탐색 자동화:
  - decay/truncation grid: `parameter_search`
  - 탐색 범위 설정: `configs/mutation_grid.json`
- 표현식 변형 자동화:
  - operator swap / window mutation / rank-zscore 변환: `mutate_expression`
- 정적검증 결합:
  - `propose_mutations(..., validator=...)`로 유효 후보만 통과 가능

## Step 12+ 인계 메모
- submit 전에는 Step 10 필터 + Step 11 변형 재검증 루프를 최소 1회 수행한다.
