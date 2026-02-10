# Step 6 실행 산출물

## 목적
시뮬 제출 전 정적검증으로 문법/스코프/타입 오류를 조기에 차단한다.

## 완료 범위
- 최소 검증기 구현:
  - `src/brain_agent/validation/static_validator.py`
  - 규칙: 허용 토큰, 괄호 균형, 호출 인자 비어있음, operator/field 존재성
- 스코프 규칙:
  - operator scope 기반 REGULAR 모드 검증
  - scope 미제공 시 non-REGULAR 제한(safe mode)
- 타입 규칙(초기 휴리스틱):
  - `ts_*`는 MATRIX 중심
  - `group_*`는 GROUP+MATRIX 조합 요구
  - VECTOR 필드의 non-`vec_*` 사용 차단
- 실패 대응 경로:
  - `ValidationReport`로 에러 목록 반환(재생성 프롬프트 입력으로 사용 가능)
- 실행 스크립트:
  - `scripts/validate_expression.sh`

## Step 7+ 인계 메모
- Step 7 파이프라인에서 `FastExpr Builder -> Static Validator -> Simulation Runner` 순으로 강제한다.
