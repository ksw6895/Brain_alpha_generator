# Operator Usage Rulebook (LLM Prior Knowledge)

## 1) 목적
- 이 문서는 LLM이 FastExpr를 생성할 때 오퍼레이터를 **문법적으로 정확하고 일관되게** 사용하기 위한 규칙집이다.

## 2) 기본 문법 규칙

### 2.1 호출 형식
- 기본 형식: `op(arg1, arg2, ...)`
- `MUST`: 함수명과 `(`를 분리하지 않는다.
  - 권장: `group_neutralize(x, g)`
  - 금지: `group_neutralize` 다음 줄에서 `(` 시작

### 2.2 인자 순서
- `MUST`: positional 인자는 정의 순서를 따른다.
- `MUST`: named 인자는 positional 뒤에 둔다.
  - 예: `bucket(rank(cap), range="0,1,0.1")`

### 2.3 파라미터 표기
- 문자열 파라미터는 따옴표로 감싼다.
  - `driver="cauchy"`
  - `range="0,1,0.1"`
- 실수 파라미터는 명시적으로 소수 표기 가능.
  - `hump=0.001`

## 3) 타입 호환 규칙

### 3.1 MATRIX 입력
- 대부분 연산의 기본 입력 타입.

### 3.2 VECTOR 입력
- `MUST`: `vec_` 계열로 집계 후 사용.
- `MUST NOT`: VECTOR를 바로 `ts_`, `rank`, `zscore`에 입력.

### 3.3 GROUP 입력
- `group_neutralize(x, group)` 2번째 인자는 GROUP 표현식이어야 한다.
- GROUP 생성은 `bucket(...)` 패턴을 기본으로 사용한다.

## 4) 연산자군별 실무 규칙

### 4.1 Time Series (`ts_`)
- 용도: 종목별 시계열 요약/변화량 추출
- 규칙:
  - lookback(`d`)는 전략 시간축과 맞춰 설정
  - 결측 필드는 `ts_backfill` 후 사용 고려

### 4.2 Cross Sectional (`rank`, `zscore`, `quantile`, `scale`)
- 용도: 동시점 종목 간 비교/정규화
- 규칙:
  - 동일 단계에서 과도한 중복 정규화 금지
  - 분포 변환(`quantile`)은 목적 명확할 때만 사용

### 4.3 Logical / Conditional (`if_else`, 비교연산)
- 용도: 필터/증폭/분기
- 규칙:
  - 조건식은 불리언 결과를 명확히 반환해야 함
  - 과도한 조건 중첩 금지

### 4.4 Execution Control (`trade_when`, `hump`, `ts_decay_linear`)
- 용도: turnover/신호 변경 속도 제어
- 규칙:
  - 신호 품질과 실행 가능성 간 균형 목적으로 사용
  - 기본 신호 생성 이전이 아니라 이후 단계에 배치

## 5) 표준 사용 패턴

### 5.1 Group neutralization
```txt
g = bucket(rank(cap), range="0,1,0.1");
x = group_neutralize(raw_signal, g);
```

### 5.2 Conditional update
```txt
entry = abs(returns) < 0.08;
alpha = trade_when(entry, signal, 0);
```

### 5.3 Turnover control
```txt
final_alpha = hump(ts_decay_linear(signal, 5), hump=0.001);
```

## 6) 금지 패턴
- metadata에 없는 오퍼레이터 호출
- scope 불일치 오퍼레이터 사용
- 인자 순서 오류
- 함수명-괄호 분리 줄바꿈
- GROUP/MATRIX/VECTOR 타입 혼용 오류
- 불필요한 연산자 중첩

## 7) LLM 강제 체크리스트
- [ ] operator 이름이 `operators_latest.json`에 존재
- [ ] 호출 시그니처(인자 수/순서) 일치
- [ ] named parameter 표기 일치
- [ ] 타입 호환성 위반 없음
- [ ] 그룹/벡터 특수 규칙 준수

## 8) 참조
- `data/meta/operators_latest.json`
- `docs/Brain Navigator Content.pdf`
