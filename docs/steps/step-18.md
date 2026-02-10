# Step 18

## FastExpr 지식팩 구축 (API + 실전 예시 기반)

## 0) 이 문서만 읽은 신규 에이전트용 요약
- step-17이 만든 retrieval pack은 "무엇을 줄일지"를 해결한다.
- step-18은 LLM이 FastExpr를 제대로 쓰게 하는 "문법/패턴 지식"을 만든다.
- 핵심은 `/operators` 정의 + `OPTIONS /simulations` 허용값 + 실전 alpha 예시를 결합한 지식팩이다.
- 목적은 생성 품질 향상이지, 거대 문법서를 만드는 것이 아니다.
- 성공 예시만 축적하면 보수적으로 수렴하므로, 실패/경계 사례도 함께 지식화한다.

## 1) 배경과 의도
### 1.1 문제
- 단순 프롬프트만으로는 operator 인자/스코프 위반이 자주 발생한다.
- 문법 지식이 약하면 정적검증 실패가 반복된다.

### 1.2 step-18 목표
- FastExpr 생성에 필요한 최소 지식을 구조화하여 재사용 가능한 팩으로 만든다.
- LLM은 이 팩 + retrieval pack만으로 expression을 생성하도록 제한한다.

## 2) 데이터 소스
### 2.1 필수
- `/operators` 메타데이터
  - `name`, `definition`, `scope`, `category`, `description`
- `OPTIONS /simulations`
  - settings allowed values (`language`, `region`, `universe`, `delay`, `neutralization` 등)

### 2.2 선택
- 계정 내 시뮬 성공 alpha expression 샘플
- 내부 fixture 샘플

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

## 4) 구현 파일 가이드
- 신규(권장): `src/brain_agent/generation/knowledge_pack.py`
- 수정: `src/brain_agent/cli.py`
  - `build-knowledge-pack` 서브커맨드 추가

## 5) 품질 규칙
1. definition/scope 누락 operator는 별도 목록으로 저장
2. examples pack은 정적검증 통과본만 포함
3. 설정 allowed values는 metadata sync 시점과 timestamp를 함께 저장
4. pack 생성 실패 시 부분 성공/실패 항목을 명시적으로 출력
5. 성공 예시만 쓰지 않고 counter-example/fix hint를 같이 제공
6. examples는 고빈도 패턴 편향을 줄이기 위해 subcategory 다양성을 확보

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

## 7) 완료 정의 (Definition of Done)
- [ ] knowledge pack 3종이 생성 가능
- [ ] 지식팩 스키마가 코드로 고정됨
- [ ] validation 통과 examples만 포함됨
- [ ] counter-example/fix hint 팩이 추가됨
- [ ] step-19가 소비할 입력 포맷이 확정됨

## 8) 다음 step 인계
- step-19에서 Idea Researcher / Alpha Maker 계약에 이 지식팩 필드를 연결한다.
- step-19 착수 전, pack 필드명/구조는 동결한다.
