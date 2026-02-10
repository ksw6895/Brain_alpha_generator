# Step 8 실행 산출물

## 목적
IdeaSpec/CandidateAlpha/AlphaResult 표준 스키마를 코드와 예시 파일로 고정한다.

## 완료 범위
- 스키마 구현:
  - `src/brain_agent/schemas.py`
    - `IdeaSpec`
    - `CandidateAlpha`
    - `AlphaResult`
- 예시 산출물:
  - `docs/artifacts/step-08/ideaspec.example.json`
  - `docs/artifacts/step-08/candidate_alpha.example.json`
  - `docs/artifacts/step-08/alpha_result.example.json`

## Step 9+ 인계 메모
- Step 9 시뮬레이션 입력은 `CandidateAlpha` 스키마만 허용한다.
- Step 10 평가는 `AlphaResult` 스키마 기준으로 수행한다.
