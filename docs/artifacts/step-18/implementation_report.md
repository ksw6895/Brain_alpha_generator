# Step 18 Implementation Report

기준일: 2026-02-11

## 1) 코드 변경 파일
- `src/brain_agent/generation/knowledge_pack.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/validation/static_validator.py`
- `src/brain_agent/validation/__init__.py`
- `src/brain_agent/generation/__init__.py`

## 2) 규칙 반영 범위 (`docs/rules` 기준)
- `operator-usage-rules-from-alpha-samples.md`
  - operator signature/scope 기반 카드 생성
  - `ts_`, `group_`, `vec_`, `trade_when/if_else`, `hump/ts_decay_linear` 팁 반영
- `data-field-type-rules-from-alpha-samples.md`
  - 예시 표현식에 MATRIX/GROUP/VECTOR 타입 규칙 반영
  - VECTOR는 `vec_` 사용 예시로 분리
- `alpha-construction-rules-and-output-semantics.md`
  - examples 태그에 `regular-signal`/정규화/turnover-control 계열 정보 반영
  - counterexamples/fix_hint를 통해 규칙 위반 복구 경로 명시

## 3) 실행/검증 커맨드와 결과

### 3.1 knowledge pack 생성
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-knowledge-pack \
  --output-dir data/meta/index
```

실행 결과 요약:
- `success: true`
- 생성 파일:
  - `data/meta/index/operator_signature_pack.json`
  - `data/meta/index/simulation_settings_allowed_pack.json`
  - `data/meta/index/fastexpr_examples_pack.json`
  - `data/meta/index/fastexpr_counterexamples_pack.json`
  - `data/meta/index/fastexpr_visual_pack.json`
- 카운트:
  - operators: 85
  - settings keys: 6
  - examples: 5
  - counterexamples: 7
  - visual operators: 85
- fallback 사용 여부: `false`

### 3.2 검증 항목 점검
1. pack 생성
- 필수 pack + counterexample + visual pack 생성 완료

2. operator 일관성
- DB operators 개수(85) == operator_signature_pack operators 개수(85)

3. examples 최소 개수/유효성
- examples 5개 생성
- `validation_passed=true`만 포함

4. counterexample 필드
- 모든 case가 `error_type`, `fix_hint` 포함

5. visual pack 구조
- `operators`, `error_taxonomy`, `example_cards` 포함

6. taxonomy 연결성
- `src/brain_agent/validation/static_validator.py`의 `VALIDATION_ERROR_TAXONOMY`를
  visual pack의 `error_taxonomy`로 그대로 변환

## 4) 실패 케이스와 재현 방법

### 4.1 simulations options 미존재
재현:
1. `data/meta/simulations_options.json` 삭제
2. fixture도 없는 환경에서 `build-knowledge-pack` 실행

예상:
- `simulation_settings_allowed_pack` 생성 실패
- CLI 결과 `failed_parts.simulation_settings_allowed_pack`에 오류 메시지 기록

대응:
1. `PYTHONPATH=src bash scripts/sync_options.sh` 실행
2. knowledge pack 재생성

### 4.2 examples 전부 검증 실패
재현:
1. operators/fields 메타가 비어 있는 DB에서 실행

예상:
- examples fallback까지 실패 시 `fastexpr_examples_pack` 실패로 보고

대응:
1. `sync-metadata`로 operators/fields 동기화
2. knowledge pack 재생성

## 5) 다음 step 진입 조건
1. step-19는 `operator_signature_pack`, `simulation_settings_allowed_pack`, `fastexpr_examples_pack`, `fastexpr_visual_pack`을 입력 계약으로 소비한다.
2. step-21에서 사용할 에러 키는 `VALIDATION_ERROR_TAXONOMY` 기준으로 고정한다.
3. step-19 착수 전, pack 필드명/구조 변경 금지.
