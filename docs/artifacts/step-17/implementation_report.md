# Step 17 Implementation Report

기준일: 2026-02-11

## 1) 코드 변경 파일
- `src/brain_agent/retrieval/pack_builder.py`
- `src/brain_agent/retrieval/__init__.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/generation/prompting.py`
- `configs/retrieval_budget.json`

## 2) 실행/검증 커맨드와 결과
### 2.1 retrieval pack 생성
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/retrieval_pack.json
```

결과 요약:
- `candidate_counts`: `{"subcategories": 5, "datasets": 15, "fields": 72, "operators": 60}`
- `token_estimate`: `{"input_chars": 19452, "input_tokens_rough": 4863}`
- 출력 파일 생성: `/tmp/retrieval_pack.json`

### 2.2 budget config fallback 검증
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --budget-config /tmp/not_exists.json \
  --output /tmp/retrieval_pack_default_budget.json
```

결과 요약:
- config 파일이 없어도 default budget으로 생성 성공

### 2.3 스키마/계약 핵심 검증
- `candidate_fields`, `candidate_operators` 비어있지 않음
- `token_estimate` 포함
- `operators`, `datasets`, `data_fields` full dump key 미포함
- `build_gated_fastexpr_prompt()`가 `RetrievalPack.context_guard.full_metadata_blocked`를 검사하여
  full metadata 유입을 코드 레벨에서 차단
- prompt builder는 `retrieval_pack`의 요약 필드만 사용하고 `visual_graph/telemetry`는 제외
- `visual_graph` 검증:
  - node types: `idea|subcategory|dataset|field|operator`
  - lane values: `exploit|explore`
  - state values: `selected|searching|dropped`
  - edge kinds: `retrieval_match|contains_dataset|contains_field|supports_operator`
- DB 이벤트 확인:
  - `event_type = retrieval.pack_built`
  - payload 키: `idea_id`, `query`, `selected_subcategories`, `candidate_counts`, `token_estimate`, `budget_policy`, `expansion_policy`, `output`

## 3) 실패 케이스와 재현 방법
### 3.1 메타데이터 미동기화 상태
재현:
1. 빈 DB 또는 datasets가 없는 target 상태에서 `build-retrieval-pack` 실행

예상 결과:
- `RuntimeError` 발생
- 메시지: `Run sync-metadata first ...`

대응:
1. `PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000`
2. retrieval pack 재생성

## 4) 다음 step 진입 조건
1. step-18은 `RetrievalPack`의 `candidate_*`, `lanes`, `context_guard`, `expansion_policy`를 그대로 입력으로 사용한다.
2. step-18 착수 전 `RetrievalPack` 필드명 변경 금지.
3. knowledge pack 생성 결과를 `build-retrieval-pack` 출력과 조합해 LLM 입력을 구성한다.
