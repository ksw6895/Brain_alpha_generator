# Step 19

## 2-Agent 계약 설계 (Idea Researcher / Alpha Maker)

## 0) 이 문서만 읽은 신규 에이전트용 요약
- 이 프로젝트는 "아이디어 생성"과 "표현식 생성"을 분리한 2-agent 구조를 목표로 한다.
- Idea Researcher는 무엇을 풀지 정의하고, Alpha Maker는 실제 FastExpr를 만든다.
- 핵심은 역할 분리보다 "입출력 계약"을 엄격히 고정하는 것이다.
- 계약이 불안정하면 디버깅 불가 상태가 된다.
- parse 오류는 의미 실패가 아닌 포맷 실패일 수 있으므로, 폐기 전에 포맷 복구 단계를 둔다.

## 1) 배경과 의도
### 1.1 왜 분리하는가
- 한 모델이 아이디어 + 표현식을 동시에 만들면 컨텍스트가 커지고 실패 원인 분리가 어렵다.
- 2-agent 구조는 비용/추적성/재시도 정책을 분리하기 쉽다.

### 1.2 step-19 목표
- 두 agent 간 JSON 계약을 코드 스키마로 고정
- 실패 시 어느 agent에서 문제인지 즉시 판단 가능하게 설계

## 2) Agent 역할 정의
### 2.1 Idea Researcher
입력:
- category/subcategory 개요
- 최근 성과 요약(선택)
- 타겟 시장 설정

출력:
- `IdeaSpec`
- 필수: `idea_id`, `hypothesis`, `keywords_for_retrieval`, `target`, `candidate_subcategories`
- 권장: `exploration_intent` (왜 이 아이디어가 탐색 가치가 있는지 1문장)

### 2.2 Alpha Maker
입력:
- IdeaSpec
- retrieval pack (step-17)
- knowledge pack (step-18)

출력:
- `CandidateAlpha`
- 필수: `simulation_settings.type=REGULAR`, `language=FASTEXPR`, `regular`, `generation_notes`
- 권장: `generation_notes.candidate_lane` (`exploit` 또는 `explore`)

## 3) 구현 범위
### 3.1 스키마
- `src/brain_agent/schemas.py` 확장
  - `IdeaSpec`에 `candidate_subcategories` 추가
  - 필요 시 `retrieval_context_id` 추가

### 3.2 프롬프트/파서 계약
- `src/brain_agent/generation/prompting.py`에
  - Idea Researcher prompt builder
  - Alpha Maker prompt builder
  - strict parse 실패 시 에러 코드 분류

### 3.3 오케스트레이션 뼈대
- 신규(권장): `src/brain_agent/agents/llm_orchestrator.py`
- 단계:
  1. idea 생성
  2. retrieval pack 생성
  3. alpha 생성
  4. parse/스키마 검증

## 4) 실패 처리 계약
1. Idea parse 실패
- 1차: 포맷 복구 전용 재시도(JSON shape만 교정, 의미는 유지)
- 2차: 일반 재생성(최대 2~3회)
- 포맷 복구 후에도 실패하면 해당 주제 폐기

2. Alpha parse 실패
- JSON repair prompt로 재시도(의미 변경 최소화)

3. 스키마 통과 후 validation 실패
- step-21의 repair 루프로 넘김

## 5) 검증 커맨드 (완료 기준)
예시(엔트리포인트 이름은 구현 시 확정):
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-idea-agent \
  --input docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/idea_out.json

PYTHONPATH=src python3 -m brain_agent.cli run-alpha-maker \
  --idea /tmp/idea_out.json \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index \
  --output /tmp/candidate_alpha.json
```

검증 항목:
1. 두 단계 모두 JSON parse 성공
2. `CandidateAlpha` schema validate 성공
3. `generation_notes.used_fields/operators`가 실제 사용값과 불일치하지 않음
4. parse 실패 케이스에서 포맷 복구 단계가 먼저 실행됨

## 6) 완료 정의 (Definition of Done)
- [ ] Idea Researcher / Alpha Maker 입력/출력 계약 고정
- [ ] 스키마 변경 사항이 코드에 반영
- [ ] 파서 실패/스키마 실패 에러코드 체계화
- [ ] 포맷 복구 우선 정책(폐기 전 단계)이 반영됨
- [ ] step-20이 수집할 토큰/비용 로그 포인트가 삽입됨

## 7) 다음 step 인계
- step-20에서 이 오케스트레이션 호출 단위별 토큰/비용 예산을 강제한다.
