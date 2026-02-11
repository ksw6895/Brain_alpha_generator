# Data Field Rulebook (LLM Prior Knowledge)

## 1) 목적
- 이 문서는 LLM이 FastExpr 작성 시 데이터필드를 **선택/표기/결합**하는 규칙을 명확히 고정한다.

## 2) Source of Truth
- 필드 존재/타입/설명 기준:
  - `data/meta/by_subcategory/*.fields.json`
  - `data/meta/index/fields_by_category_summary.json`
  - `data/meta/index/fields_by_subcategory_summary.json`

## 3) 필드 표기 규칙
- `MUST`: 데이터필드는 식에서 **따옴표 없이 식별자 그대로** 사용한다.
  - 예: `close`, `returns`, `bookvalue_ps`
- `MUST`: 존재하지 않는 식별자를 데이터필드처럼 사용하지 않는다.
- `SHOULD`: 사용자 변수명과 데이터필드명 충돌을 피한다.
  - 권장: 중간 변수에 `_signal`, `_group`, `_raw` 접미사 사용

## 4) 타입별 사용 규칙

### 4.1 MATRIX
- 대부분 오퍼레이터의 기본 입력 타입.
- ratio/차분/정규화 연산에 직접 사용 가능.

### 4.2 VECTOR
- `MUST`: `vec_` 연산으로 먼저 단일값(MATRIX)으로 변환.
- `MUST NOT`: VECTOR를 직접 `ts_`, `rank`, `zscore`에 넣지 않는다.

### 4.3 GROUP
- 그룹 라벨 전용 타입.
- `group_neutralize`의 2번째 인자 등 그룹 문맥에서만 사용.
- 그룹 필드가 없으면 `bucket(...)`으로 그룹 생성.

### 4.4 SYMBOL / UNIVERSE
- 수치 신호 계산 입력으로 사용하지 않는다.

## 5) 필드 선택 규칙
- 1차: 아이디어와 의미가 맞는 필드 선택 (`description` 근거)
- 2차: 설정 호환성 확인 (`region`, `universe`, `delay`)
- 3차: 타입 적합성 확인 (MATRIX/VECTOR/GROUP)
- 4차: 결측/희소성 위험 확인

## 6) 결측/희소성 처리 규칙
- 결측 가능성이 큰 필드:
  - `ts_backfill(x, d)` 또는 조건부 처리 적용
- 희소 그룹:
  - 그룹 수 완화, 필요 시 densify 계열 고려
- `MUST`: 결측치 처리 없는 원시 희소 필드를 핵심 신호에 바로 쓰지 않는다.

## 7) 결합 규칙 (ratio/spread/합성)
- 분모가 작거나 0에 가까운 조합은 안정화 상수(예: `+0.001`) 고려.
- 단위/스케일이 다른 필드 결합 시 정규화(`rank`/`zscore`/`scale`)를 적용.
- 이벤트성/저빈도 필드는 lookback/backfill과 함께 사용.

## 8) 누출 방지 규칙
- `MUST`: delay 가정 위반 금지(미래값/동시점 미사용 정보 참조 금지).
- `MUST`: 현재 시점에서 관측 가능한 정보만 사용.
- `SHOULD`: 데이터 시간 가정(특히 delay 0 vs 1)을 로그에 남긴다.

## 9) FastExpr 작성 시 구체 규칙
- 중간 변수 문장 끝은 `;`
- 마지막 반환줄은 단일 변수/식
- 필드 자체에 함수처럼 `()`를 붙이지 않는다.
- 함수 파라미터 문자열 표기 통일:
  - `range="0,1,0.1"` 형태 권장

## 10) 금지 패턴
- 존재하지 않는 필드 사용
- 타입 위반 사용(VECTOR 직접 연산, GROUP 수치연산 오용)
- 설정 비호환 필드 사용
- 결측/스케일 처리 없는 무리한 결합

## 11) 최소 체크리스트
- [ ] 필드 존재 확인 완료
- [ ] 설정 호환성 확인 완료
- [ ] 타입 규칙 위반 없음
- [ ] 결측/희소성 대응 포함
- [ ] 단위/스케일 정규화 고려 완료
- [ ] 누출 위험 점검 완료

## 12) 참조
- `data/meta/by_subcategory/*.fields.json`
- `data/meta/index/fields_by_category_summary.json`
- `data/meta/index/fields_by_subcategory_summary.json`
- `docs/Brain Navigator Content.pdf`
