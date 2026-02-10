# Step 6

## FastExpr “정적 검증” 최소 규칙 (시뮬 실패율을 줄이는 장치)


> 완전한 타입 시스템을 처음부터 구현하기 어렵다면,
> **(1) 토큰 검증 + (2) 괄호/인자 개수 + (3) 필드/연산자 존재성 + (4) 스코프 규칙**만으로도
> 시뮬 실패율을 크게 줄일 수 있다.

### 6.1 토큰/문법 최소 검증

* 허용 토큰:

  * operator name (from /operators)
  * data field id (from /data-fields)
  * 숫자 상수(정수/소수)
  * 괄호 (), 콤마, 공백
* 괄호 밸런스 체크
* “함수 호출” 패턴: `name(arg1, arg2, ...)`

### 6.2 스코프(scope) 규칙

* operator.scope가 제공되는 경우:

  * REGULAR: regular 식에서만 사용
  * SELECTION/COMBO: SuperAlpha에서만 사용
* scope 정보가 없으면:

  * 우선은 REGULAR만 사용하도록 whitelist(안전 모드) 운영

### 6.3 필드 타입(type) 규칙(점진적 강화)

* data field type이 MATRIX/VECTOR/GROUP/UNIVERSE로 제공될 수 있다.
* 초기 안전 규칙(예):

  * Time-series 계열(ts_*)은 MATRIX 입력만 허용
  * Group 계열(group_*)은 GROUP + MATRIX 조합만 허용
  * VECTOR 필드는 “벡터 연산자(예: vec_*)”로 먼저 변환하거나, VECTOR을 허용하는 operator에만 연결
* 이 규칙은 운영하면서 “실패 로그 기반”으로 점진적으로 확장한다.

### 6.4 정적 검증 실패 시 행동

* 즉시 재생성(rewrite) 요청:

  * “사용 불가 operator/field” 목록을 LLM에 돌려주고 수정하도록 한다.
* “연속 3회 실패”하면:

  * 해당 아이디어를 폐기 or 더 안전한 템플릿으로 다운그레이드

---


## 체크리스트
- [ ] 토큰/문법 최소 검증
- [ ] 스코프(scope) 규칙
- [ ] 필드 타입(type) 규칙(점진적 강화)
- [ ] 정적 검증 실패 시 행동
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
