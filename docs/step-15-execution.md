# Step 15 실행 산출물

## 목적
장기 운영 전략(초기 안정화 → 확장 → 포트폴리오 운영)을 실행 가능한 가이드로 정리한다.

## 완료 범위
- 운영 전략 문서:
  - `docs/artifacts/step-15/operating_strategy.md`
- 코드 대응 포인트:
  - 초기 안정화: `src/brain_agent/validation/static_validator.py`
  - 확장/탐색: `src/brain_agent/feedback/mutator.py`
  - 포트폴리오/상관 관리: `src/brain_agent/evaluation/evaluator.py`

## Step 16+ 인계 메모
- 외부 라이브러리(wqb/ACE) 도입 여부를 운영 요구(속도/유지보수성)에 따라 선택한다.
