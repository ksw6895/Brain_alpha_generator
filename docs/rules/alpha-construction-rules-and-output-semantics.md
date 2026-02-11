# Alpha Construction Rulebook and FastExpr Output Semantics

## 1) 범위 구분 (중요)

### 1.1 CandidateAlpha 규칙
- `CandidateAlpha`는 **JSON 출력 포맷** 규칙이다.
- 즉, 아래를 정확히 맞춘다는 의미다:
  - `idea_id`
  - `alpha_id` (보통 `null`)
  - `simulation_settings` (`type`, `settings`, `regular`)
  - `generation_notes`

### 1.2 FastExpr 규칙
- 실제 알파 식 규칙은 `simulation_settings.regular` 문자열 내부의 **FastExpr 스크립트 문법**이다.
- 사용자가 요구한 세미콜론/줄바꿈 규칙은 이 FastExpr 레이어에 적용된다.

## 2) FastExpr 스크립트 작성 규칙 (문법)

### 2.1 문장 단위
- 중간 변수 할당 문장 형식:
  - `<var_name> = <expression>;`
- `MUST`: **마지막 반환 줄을 제외한 모든 문장 끝에 `;`를 붙인다.**
- `MUST`: 줄바꿈으로 문장을 끊더라도 문장 종료는 `;`로 명시한다.

### 2.2 최종 반환
- 마지막 줄은 아래 둘 중 하나:
  1. 최종 변수명 단독 (`final_alpha`)
  2. 최종 식 단독 (`hump(..., hump=0.001)`)
- `SHOULD`: 마지막 줄에는 `;`를 생략한다(표준 출력 라인으로 취급).

### 2.3 함수 호출 줄바꿈
- `MUST`: 함수명과 여는 괄호는 같은 줄에 둔다.
  - 권장: `group_neutralize(x, g)`
  - 비권장: `group_neutralize` 다음 줄에 `(` 시작
- 긴 인자는 괄호 내부에서만 줄바꿈한다.

### 2.4 주석 규칙
- `#` 또는 `//` 주석 사용 가능.
- `SHOULD`: 한 문서/한 알파에서 주석 스타일 하나로 통일한다.
- `MUST NOT`: 주석이 식 중간 토큰을 깨도록 삽입하지 않는다.

### 2.5 토큰/표기 규칙
- 변수명/필드명: `snake_case` 권장.
- 문자열 인자(예: `range`, `driver`)는 따옴표 사용.
  - 예: `range="0,1,0.1"`, `driver="cauchy"`
- 비교/논리 연산(`>`, `<`, `==`)은 조건식에서만 사용한다.

## 3) 연산 단계 규칙 (구조)

### 3.1 권장 단계
1. Raw signal 생성
2. 정규화 (`rank`/`zscore`/`ts_zscore`)
3. 조건부 실행 (`if_else`/`trade_when`) 필요 시 적용
4. 중립화 (`group_neutralize` 또는 settings neutralization)
5. turnover 제어 (`hump`/`ts_decay_linear`/settings decay)
6. 최종 반환

### 3.2 중복 방지
- 같은 목적의 연산을 과도하게 중복하지 않는다.
  - 예: 불필요한 다중 정규화, 다중 중립화 연쇄

## 4) 자주 쓰는 표준 패턴

### 4.1 기본 템플릿
```txt
raw_signal = <signal_expr>;
normalized_signal = <normalization_expr>;
group_signal = group_neutralize(normalized_signal, <group_expr>);
final_alpha = hump(ts_decay_linear(group_signal, 5), hump=0.001);
final_alpha
```

### 4.2 조건부 거래 템플릿
```txt
entry = <boolean_condition>;
exit = <boolean_condition_or_0_or_-1>;
raw_alpha = trade_when(entry, <alpha_expr>, exit);
raw_alpha
```

## 5) 데이터 타입 결합 규칙 (요약)
- MATRIX: 일반 연산에 직접 사용 가능
- VECTOR: `vec_` 계열로 집계 후 사용
- GROUP: 그룹 연산의 그룹 입력으로 사용
- `group_neutralize(x, group)`의 2번째 인자는 GROUP 표현식이어야 한다.

## 6) 출력값 의미 (해석)
- `regular` 식의 결과는 “즉시 수익률”이 아니라 종목별 신호값이다.
- 시뮬레이터는 신호를 중립화/정규화/북사이즈 반영 후 포지션으로 변환한다.
- 따라서 성과는 식 자체 + 설정(Neutralization/Decay/Truncation 등)의 합성 결과다.

## 7) 금지 규칙
- 마지막 줄이 없거나, 마지막 줄이 반환 표현식이 아닌 경우
- 중간 문장 세미콜론 누락
- 함수명과 `(` 분리 줄바꿈
- 존재하지 않는 operator/field 사용
- 타입 불일치 입력(VECTOR 직접 사용 등)

## 8) 최소 검증 체크리스트
- [ ] 중간 문장 모두 `;` 종료
- [ ] 마지막 줄은 반환식(변수 또는 식) 1개
- [ ] 함수 호출 문법 일관성 유지
- [ ] operator/field가 metadata에 존재
- [ ] 타입 규칙 위반 없음
- [ ] parse 실패 시 `포맷 복구 -> 재생성` 순서 적용

## 9) 참조
- `docs/Brain Navigator Content.pdf`
- `data/meta/operators_latest.json`
- `data/meta/by_subcategory/*.fields.json`
