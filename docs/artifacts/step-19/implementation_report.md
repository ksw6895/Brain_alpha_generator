# Step 19 Implementation Report

기준일: 2026-02-11

## 1) 코드 변경 파일
- `src/brain_agent/generation/openai_provider.py`
- `src/brain_agent/agents/llm_orchestrator.py`
- `src/brain_agent/cli.py`
- `src/brain_agent/generation/__init__.py`
- `src/brain_agent/schemas.py`
- `src/brain_agent/runtime/event_bus.py`
- `src/brain_agent/server/app.py`
- `src/brain_agent/storage/sqlite_store.py`
- `src/brain_agent/storage/event_log.py`
- `src/brain_agent/simulation/runner.py`
- `src/brain_agent/agents/pipeline.py`
- `README.md`
- `.env.example`
- `requirements.txt`

## 2) 반영 범위 요약
1. OpenAI SDK 기반 실제 2-agent 생성 경로 추가
- `OpenAIResponsesJSONClient` 도입
- `responses.create()` + `text.format.type=json_schema` + `strict=true`로 Structured Output 강제
- Idea/Alpha 각각 별도 JSON Schema 적용

2. 모델/추론 파라미터 기본값 고정
- 기본 모델: `gpt-5.2`
- `reasoning.effort=medium`
- `text.verbosity=medium`
- `reasoning.summary=auto`
- CLI/환경변수로 재정의 가능

3. 오케스트레이터 LLM provider 모드
- `llm_provider=openai|mock|auto`
- `openai`: API 키/SDK 없으면 즉시 오류
- `auto`: OpenAI 사용 가능 시 사용, 불가 시 mock fallback
- `mock`: 오프라인 계약 검증용 생성

4. parse/repair + 이벤트 계약 유지
- strict parse 실패 시 `repair_json_text()` 우선
- `agent.idea_parse_failed`, `agent.idea_repair_attempted`, `agent.alpha_parse_failed`, `agent.alpha_repair_attempted` 유지
- `llm.usage_point` payload에 provider/model/reasoning/usage 추가

5. 실시간 브리지 골격 유지
- DB(event_log) payload와 `/ws/live` 송신 payload 동일 구조 유지

## 3) 실행/검증 커맨드와 결과

### 3.1 mock provider로 idea/alpha 실행
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-idea-agent \
  --llm-provider mock \
  --input docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/idea_out_openai_mock2.json

PYTHONPATH=src python3 -m brain_agent.cli run-alpha-maker \
  --llm-provider mock \
  --idea /tmp/idea_out_openai_mock2.json \
  --retrieval-pack /tmp/retrieval_pack_step19.json \
  --knowledge-pack-dir data/meta/index \
  --output /tmp/candidate_alpha_openai_mock2.json
```
결과 요약:
- 두 명령 모두 성공
- `llm_provider=mock`, `llm_model=gpt-5.2` 출력 확인

### 3.2 OpenAI provider 키 미설정 실패 경로 확인
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-idea-agent \
  --llm-provider openai \
  --input docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/idea_out_openai_real.json
```
결과 요약:
- 종료코드 2
- `{"error":"openai_provider_error","message":"OPENAI_API_KEY is not set"}`

### 3.3 usage 이벤트 payload 확인
요약:
- `llm.usage_point.payload.provider=model/reasoning` 필드 저장 확인
- 예시: `provider=mock`, `model=gpt-5.2`, `reasoning={effort:medium, summary:auto, verbosity:medium}`

## 4) 실패 케이스와 재현 방법

### 4.1 OpenAI SDK 미설치
재현:
- `openai` 패키지 없는 환경에서 `--llm-provider openai` 실행

결과:
- `openai_provider_error` 반환

대응:
1. `pip install -r requirements.txt`
2. `OPENAI_API_KEY` 설정 후 재실행

### 4.2 API 키 미설정
재현:
- `OPENAI_API_KEY` 없이 `--llm-provider openai` 실행

결과:
- `OPENAI_API_KEY is not set`

대응:
1. `.env` 또는 환경변수에 키 설정
2. 필요 시 `--llm-provider auto` 또는 `mock` 사용
3. parse/repair 테스트만 필요하면 `--raw-output <file>`를 함께 사용하면 키 없이도 검증 가능

## 5) OpenAI 문서 조사 반영 포인트
- Responses API 기준으로 reasoning/text.format 파라미터를 사용
- Structured Output은 `json_schema + strict` 방식으로 강제
- 모델 기본값은 user 요청에 따라 `gpt-5.2` 적용

## 6) 다음 step 진입 조건
1. step-20에서 `llm.usage_point.payload.usage`를 budget telemetry로 집계한다.
2. step-20 budget fallback 시 `llm_provider=openai` 호출 전 prompt budget gate를 적용한다.
3. step-21에서 validation-first repair loop를 OpenAI 재호출 분기와 연결한다.
