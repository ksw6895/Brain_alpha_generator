# Step 12 실행 산출물

## 목적
제출 기능을 옵션 모듈로 분리해 계정/정책 차이에 안전하게 대응한다.

## 완료 범위
- 제출 API 래퍼(옵션):
  - `src/brain_agent/brain_api/submit.py`
    - `submit_alpha`
    - `get_submit_status`
- 제출 전 체크리스트 템플릿:
  - `docs/artifacts/step-12/pre_submit_checklist.md`
- 안전 기본값:
  - 제출 로직은 파이프라인 기본 경로에서 자동 호출하지 않음

## Step 13+ 인계 메모
- 다양성 정책 점수를 포함해 제출 큐 우선순위를 다시 계산한 뒤 submit 모듈을 호출한다.
