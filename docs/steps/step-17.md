# Step 17

## LLM 컨텍스트 게이팅 + Top-K Retrieval 강제

## 0) 이 문서만 읽은 신규 에이전트용 요약
- 이 프로젝트의 목적은 "LLM으로 FastExpr 알파를 생성"하는 것이다.
- 그러나 `data_fields` 전체를 LLM에 넣으면 비용/지연/환각이 폭발한다.
- 따라서 LLM 입력은 반드시 "아이디어별 Top-K subset"으로 제한해야 한다.
- step-17의 핵심 산출물은 `retrieval pack`(LLM 입력용 압축 컨텍스트)이다.
- step-17에서 프론트엔드의 "Neural Cosmos(마인드맵/네트워크)" 데이터 계약도 함께 동결한다.
- step-17이 끝나야 step-18~21의 생성/수정 루프를 안전하게 구현할 수 있다.
- 단, 비용 절감 때문에 탐색력을 잃지 않도록 exploit/explore 이중 예산을 같이 설계해야 한다.

## 1) 배경과 의도
### 1.1 현재 시스템
- metadata sync는 구현되어 있으며 DB/JSON 인덱스가 존재한다.
- keyword retrieval 구현이 존재한다.
- 정적검증기, 시뮬레이션, 평가기는 구현되어 있다.

### 1.2 현재 문제
- 메타데이터를 그대로 LLM에 전달하면 토큰 비용이 과도하다.
- LLM이 존재하지 않는 field/operator를 생성할 가능성이 높다.
- 결과적으로 시뮬 실패율과 재시도 비용이 동시 증가한다.
- 반대로 과도한 Top-K 축소는 탐색 다양성을 망가뜨려 리서치 품질을 저하시킬 수 있다.

### 1.3 step-17의 역할
- LLM이 쓸 "작은 입력 묶음"을 표준화한다.
- 아이디어 단위로 관련 subcategory/dataset/field/operator만 전달한다.

## 2) 구현 범위
### 2.1 반드시 할 일
1. retrieval pack 스키마 고정
2. subcategory 선별 규칙 정의
3. Top-K budget 기본값 정의 (exploit/explore 분리)
4. prompt에 full metadata 유입 차단 규칙 정의
5. 반복 오류 시 retrieval 확장 트리거 정의
6. 프론트 시각화용 retrieval graph(노드/엣지/lane) 계약 정의
7. retrieval 단계 이벤트 스키마 정의 (`retrieval.*`)

### 2.2 하지 말아야 할 일
- LLM 생성기 자체를 먼저 완성하려고 하지 않는다.
- 비용 제어(예산 소진 정책)는 step-20에서 다룬다.
- repair loop 자동화는 step-21에서 다룬다.

### 2.3 프론트 동시 착수 범위 (F17: Neural Cosmos v0)
- 목적: 유저가 "AI가 지금 어떤 데이터 필드/연산자를 수색 중인지"를 실시간으로 볼 수 있게 한다.
- 최소 구현:
  1. retrieval pack에 시각화용 그래프 데이터(`visual_graph`)를 포함
  2. exploit/explore lane을 노드 단위로 태깅
  3. 상태 컬러 의미를 계약으로 고정 (`searching`: 붉은 계열, `selected`: 푸른 계열, `dropped`: 회색 계열)
- 주의: 3D 렌더링 구현은 프론트(Next.js) 책임이고, step-17에서는 그래프 데이터 계약만 고정한다.
- 권장 렌더러: `react-force-graph` (2D/3D 공용 데이터 포맷 재사용 가능)

## 3) 입력/출력 계약
### 3.1 입력
- `IdeaSpec.keywords_for_retrieval`
- target (`instrumentType`, `region`, `universe`, `delay`)
- 메타데이터 저장소(DB 또는 `data/meta/index/*`)

### 3.2 출력: retrieval pack
```json
{
  "idea_id": "idea_20260210_001",
  "query": "earnings surprise mean reversion",
  "target": {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1},
  "selected_subcategories": ["analyst-analyst-estimates", "earnings-earnings-estimates"],
  "candidate_datasets": [{"id": "analyst15", "name": "Earnings forecasts"}],
  "candidate_fields": [{"id": "act_q_eps_surprisemean", "dataset_id": "analyst7", "type": "MATRIX"}],
  "candidate_operators": [{"name": "rank", "definition": "rank(x)", "scope": ["REGULAR"]}],
  "lanes": {
    "exploit": {"field_ids": ["act_q_eps_surprisemean"], "operator_names": ["rank"]},
    "explore": {"field_ids": ["alt_field_001"], "operator_names": ["zscore"]}
  },
  "visual_graph": {
    "version": "v1",
    "nodes": [
      {"id": "idea:idea_20260210_001", "type": "idea", "label": "earnings surprise mean reversion", "lane": "exploit", "state": "selected", "score": 1.0},
      {"id": "subcategory:analyst-analyst-estimates", "type": "subcategory", "label": "analyst-estimates", "lane": "exploit", "state": "selected", "score": 0.88},
      {"id": "field:act_q_eps_surprisemean", "type": "field", "label": "act_q_eps_surprisemean", "lane": "exploit", "state": "searching", "score": 0.91}
    ],
    "edges": [
      {"source": "idea:idea_20260210_001", "target": "subcategory:analyst-analyst-estimates", "kind": "retrieval_match", "weight": 0.88},
      {"source": "subcategory:analyst-analyst-estimates", "target": "field:act_q_eps_surprisemean", "kind": "contains_field", "weight": 0.91}
    ]
  },
  "token_estimate": {"input_chars": 12000, "input_tokens_rough": 3500},
  "budget_policy": {"exploit_ratio": 0.7, "explore_ratio": 0.3},
  "expansion_policy": {
    "enabled": true,
    "trigger_on_repeated_validation_error": 2,
    "topk_expand_factor": 1.5
  },
  "telemetry": {
    "retrieval_ms": 183,
    "candidate_counts": {"subcategories": 5, "datasets": 16, "fields": 62, "operators": 48}
  }
}
```

## 4) 구현 파일 가이드
아래 중 하나를 선택하되, 계약은 동일해야 한다.

### 옵션 A (권장)
- 신규: `src/brain_agent/retrieval/pack_builder.py`
- 수정: `src/brain_agent/cli.py`
  - `build-retrieval-pack` 서브커맨드 추가
- 수정: `src/brain_agent/storage/sqlite_store.py`
  - `append_event("retrieval.pack_built", payload)` 저장 지점 추가
- 수정(선택): `src/brain_agent/storage/event_log.py`
  - JSONL 백업 로그에도 동일 event_type 저장

### 옵션 B
- 기존 `src/brain_agent/retrieval/keyword.py`에 pack 생성 로직 통합
- CLI는 동일하게 추가

### 4.1 코드 연결 포인트 (현재 구현 기준)
1. `src/brain_agent/retrieval/keyword.py`
- 이미 BM25/overlap retrieval이 있어 pack builder의 score source로 재사용 가능하다.
2. `src/brain_agent/metadata/organize.py`
- `data/meta/index/datasets_by_subcategory.json` 구조를 subcategory 선별 입력으로 사용한다.
3. `src/brain_agent/storage/sqlite_store.py`
- `list_datasets()`, `list_data_fields()`, `list_operators()`로 DB 기반 pack 생성 경로를 지원한다.

## 5) 알고리즘 가이드
### 5.1 subcategory 선별
1. `datasets_by_subcategory`에서 후보를 가져온다.
2. idea query와 서브카테고리 이름/meaning을 매칭한다.
3. 상위 N개 subcategory만 유지한다 (기본 3~6).

### 5.2 Top-K 기본값 (시작점)
- exploit lane:
  - subcategories: 3~6
  - datasets: 10~20
  - fields: 40~80
  - operators: 40~60
- explore lane (최소 유지):
  - subcategories: 1~2
  - datasets: 2~4
  - fields: 8~20
  - operators: 8~20

### 5.3 Explore 보존 규칙
1. 예산 압박이 있어도 explore lane을 0으로 만들지 않는다.
2. 최종 pack에는 exploit/explore 후보가 모두 포함되어야 한다.
3. explore 후보는 low-frequency subcategory 또는 낮은 노출 operator를 우선한다.

### 5.4 필터 우선순위
1. target 일치 여부
2. field type 적합성(MATRIX/GROUP/VECTOR)
3. score 상위순

### 5.5 Retrieval 확장 규칙 (중요)
1. 동일 validation 오류가 2회 이상 반복되면 축소 대신 확장을 먼저 시도한다.
2. 확장 순서:
   - fields Top-K +50%
   - operators Top-K +30%
   - subcategory +1
3. 확장 후에도 실패하면 step-21 repair loop로 넘긴다.

### 5.6 retrieval graph 생성 규칙 (Neural Cosmos 데이터 레이어)
1. 노드 타입은 `idea`, `subcategory`, `dataset`, `field`, `operator`만 허용한다.
2. 엣지 타입은 `retrieval_match`, `contains_dataset`, `contains_field`, `supports_operator`로 제한한다.
3. score는 retrieval 스코어를 0~1로 정규화한다.
4. lane은 `exploit|explore` 이외 값 금지.
5. UI 렌더러가 2D/3D를 선택할 수 있도록 레이아웃 좌표는 강제하지 않는다.

## 6) 검증 커맨드 (완료 기준)
아래를 문서화 가능한 형태로 실행/기록한다.

```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/retrieval_pack.json
```

검증 항목:
1. 출력 JSON이 스키마를 만족한다.
2. candidate_fields/ops가 비어있지 않다.
3. token_estimate가 계산된다.
4. full metadata가 output에 포함되지 않는다.
5. exploit/explore 비율 및 확장 정책 메타가 포함된다.
6. `visual_graph.nodes/edges`가 생성되고 lane/state/type 규칙을 만족한다.
7. retrieval 단계 이벤트(`retrieval.pack_built`)가 event_log에 남는다.

## 7) 완료 정의 (Definition of Done)
- [ ] retrieval pack 스키마가 코드/문서로 고정됨
- [ ] CLI 또는 함수 진입점이 생김
- [ ] 기본 Top-K budget이 config 가능하게 노출됨
- [ ] exploit/explore 이중 예산이 스키마에 반영됨
- [ ] 반복 오류 시 retrieval 확장 트리거가 정의됨
- [ ] 예시 아이디어 입력으로 재현 가능한 출력 생성 성공
- [ ] step-18이 바로 사용할 수 있는 인터페이스 제공
- [ ] 프론트용 `visual_graph` 계약이 고정됨 (Neural Cosmos v0)
- [ ] retrieval 이벤트 스키마가 고정됨 (`retrieval.*`)

## 8) 다음 step 인계
- step-18은 이 step의 retrieval pack을 입력으로 받아 FastExpr 지식팩과 결합한다.
- step-18 착수 전, 본 step의 스키마 변경은 금지한다.
