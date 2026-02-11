# Step 18

## FastExpr 지식팩 구축 (API + 실전 예시 기반)

## 0) 이 문서만 읽은 신규 에이전트용 요약
- step-17이 만든 retrieval pack은 "무엇을 줄일지"를 해결한다.
- step-18은 LLM이 FastExpr를 제대로 쓰게 하는 "문법/패턴 지식"을 만든다.
- 핵심은 `/operators` 정의 + `OPTIONS /simulations` 허용값 + 실전 alpha 예시를 결합한 지식팩이다.
- 목적은 생성 품질 향상이지, 거대 문법서를 만드는 것이 아니다.
- 성공 예시만 축적하면 보수적으로 수렴하므로, 실패/경계 사례도 함께 지식화한다.
- 프론트엔드가 raw metadata를 직접 파싱하지 않도록 "시각화 친화 요약팩"도 이 step에서 같이 만든다.

## 1) 배경과 의도
### 1.1 문제
- 단순 프롬프트만으로는 operator 인자/스코프 위반이 자주 발생한다.
- 문법 지식이 약하면 정적검증 실패가 반복된다.

### 1.2 step-18 목표
- FastExpr 생성에 필요한 최소 지식을 구조화하여 재사용 가능한 팩으로 만든다.
- LLM은 이 팩 + retrieval pack만으로 expression을 생성하도록 제한한다.
- 프론트는 이 팩을 이용해 operator/에러/예시 카드를 즉시 렌더링한다.

## 2) 데이터 소스
### 2.1 필수
- `/operators` 메타데이터
  - `name`, `definition`, `scope`, `category`, `description`
- `OPTIONS /simulations`
  - settings allowed values (`language`, `region`, `universe`, `delay`, `neutralization` 등)

### 2.2 선택
- 계정 내 시뮬 성공 alpha expression 샘플
- 내부 fixture 샘플
- `src/brain_agent/validation/static_validator.py`의 대표 에러 문자열 패턴

## 3) 산출물 계약
### 3.1 operator signature pack
경로 예시: `data/meta/index/operator_signature_pack.json`
```json
{
  "version": "v1",
  "operators": [
    {"name": "ts_delta", "definition": "ts_delta(x, d)", "scope": ["REGULAR"], "category": "Time Series"}
  ]
}
```

### 3.2 settings allowed pack
경로 예시: `data/meta/index/simulation_settings_allowed_pack.json`
```json
{
  "language": ["FASTEXPR"],
  "region": ["USA"],
  "delay": [0, 1]
}
```

### 3.3 FastExpr examples pack
경로 예시: `data/meta/index/fastexpr_examples_pack.json`
```json
{
  "version": "v1",
  "examples": [
    {
      "expression": "rank(ts_delta(log(close), 5))",
      "tags": ["starter", "price-volume"],
      "validation_passed": true
    }
  ]
}
```

### 3.4 Counter-example pack (탐색 보존)
경로 예시: `data/meta/index/fastexpr_counterexamples_pack.json`
```json
{
  "version": "v1",
  "cases": [
    {
      "expression": "group_rank(close)",
      "error_type": "group_requires_group_and_matrix",
      "fix_hint": "GROUP field + MATRIX field 조합으로 수정"
    }
  ]
}
```

### 3.5 Visual knowledge pack (프론트 소비 전용)
경로 예시: `data/meta/index/fastexpr_visual_pack.json`
```json
{
  "version": "v1",
  "operators": [
    {
      "name": "ts_delta",
      "category": "Time Series",
      "scope": ["REGULAR"],
      "signature": "ts_delta(x, d)",
      "display": {"group": "timeseries", "badge_color": "cyan", "complexity": "medium"},
      "tips": ["MATRIX 필드와 window 인자 조합", "window가 커질수록 반응성은 낮아짐"]
    }
  ],
  "error_taxonomy": [
    {
      "error_key": "unknown_operator",
      "match_pattern": "Unknown operator:",
      "severity": "high",
      "fix_hint": "retrieval pack 내 operator로 치환"
    }
  ],
  "example_cards": [
    {
      "expression": "rank(ts_delta(log(close), 5))",
      "tags": ["starter", "pv"],
      "quality_flags": {"validation_passed": true, "counterexample": false}
    }
  ]
}
```

## 4) 구현 파일 가이드
- 신규(권장): `src/brain_agent/generation/knowledge_pack.py`
- 수정: `src/brain_agent/cli.py`
  - `build-knowledge-pack` 서브커맨드 추가
- 수정(권장): `src/brain_agent/validation/static_validator.py`
  - 에러 문자열 분류용 패턴/키 매핑 상수 분리 (visual/error taxonomy 재사용 목적)

### 4.1 코드 연결 포인트 (현재 구현 기준)
1. `src/brain_agent/metadata/sync.py`
- `sync_simulation_options()` 산출물(`data/meta/simulations_options.json`)을 settings pack 입력으로 사용한다.
2. `src/brain_agent/metadata/organize.py`
- category/subcategory 인덱스(`data/meta/index/*`)를 example tag 다양성 확보에 사용한다.
3. `src/brain_agent/storage/sqlite_store.py`
- `list_operators()`, `list_data_fields()`를 지식팩 생성 입력 소스로 사용한다.

## 5) 품질 규칙
1. definition/scope 누락 operator는 별도 목록으로 저장
2. examples pack은 정적검증 통과본만 포함
3. 설정 allowed values는 metadata sync 시점과 timestamp를 함께 저장
4. pack 생성 실패 시 부분 성공/실패 항목을 명시적으로 출력
5. 성공 예시만 쓰지 않고 counter-example/fix hint를 같이 제공
6. examples는 고빈도 패턴 편향을 줄이기 위해 subcategory 다양성을 확보
7. visual pack은 프론트가 raw_json 없이 렌더링 가능한 최소 필드만 포함
8. 에러 taxonomy는 step-21 repair loop error code와 동일 키를 사용

## 6) 검증 커맨드 (완료 기준)
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-knowledge-pack \
  --output-dir data/meta/index
```

검증 항목:
1. pack 3종 파일이 생성된다.
2. operators 수와 pack 내 operators 수가 일관적이다.
3. examples가 최소 1개 이상 존재한다(없으면 fixture fallback 사용).
4. pack JSON 로딩/파싱이 실패하지 않는다.
5. counter-example pack이 생성되고 error_type/fix_hint 필드를 가진다.
6. `fastexpr_visual_pack.json`이 생성되고 operators/error_taxonomy/example_cards를 포함한다.
7. visual pack만으로 operator 카드/에러 카드 렌더링이 가능하다.

실행 증빙:
- `docs/artifacts/step-18/implementation_report.md` (2026-02-11)

## 7) 완료 정의 (Definition of Done)
- [x] knowledge pack 3종이 생성 가능
- [x] 지식팩 스키마가 코드로 고정됨
- [x] validation 통과 examples만 포함됨
- [x] counter-example/fix hint 팩이 추가됨
- [x] step-19가 소비할 입력 포맷이 확정됨
- [x] 프론트용 visual knowledge pack 스키마가 고정됨
- [x] step-21 오류 코드와 연결 가능한 error taxonomy 키가 포함됨

## 8) 다음 step 인계
- step-19에서 Idea Researcher / Alpha Maker 계약에 이 지식팩 필드를 연결한다.
- step-19 착수 전, pack 필드명/구조는 동결한다.
