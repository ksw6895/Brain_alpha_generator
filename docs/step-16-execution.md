# Step 16 실행 산출물

## 목적
wqb/ACE 활용 지점을 현재 코드 구조에 맞춰 선택적으로 흡수할 수 있도록 가이드화한다.

## 완료 범위
- 통합 노트:
  - `docs/artifacts/step-16/integration_notes.md`
- 현재 구현 상태:
  - API 직접 래퍼: `src/brain_agent/brain_api/*`
  - 필요 시 adapter 교체 가능한 계층 분리 유지
- ACE 참고 반영:
  - `ACE API [Gold]/ace_lib.py`의 시뮬/세션 패턴을 현재 모듈 구조로 재정리

## 후속 인계 메모
- 실제 운영에서 wqb/ACE를 붙일 경우 `brain_api` 계층만 교체하고 상위 파이프라인(`agents`, `simulation`, `evaluation`)은 유지한다.
