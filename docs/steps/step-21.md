# Step 21

## Validation-first 생성/수정 루프 완성

## 0) 이 문서만 읽은 신규 에이전트용 요약
- step-21은 "LLM 생성 결과를 바로 시뮬에 보내지 않도록" 파이프라인을 완성하는 단계다.
- 생성 -> 정적검증 -> 수정 -> 재검증 -> 시뮬 순서를 강제해야 한다.
- 목표는 시뮬 실패율 감소와 고비용 재시도 감소다.
- 단, 반복 실패에서 같은 후보만 맴돌지 않도록 포맷 복구/검색 확장 분기를 함께 둔다.

## 1) 배경과 의도
### 1.1 현재 문제
- 생성된 CandidateAlpha를 즉시 시뮬하면 문법/타입/스코프 오류로 실패한다.
- 실패 시 API 호출 비용과 시간이 낭비된다.

### 1.2 목표
- validation-first gate를 표준 경로로 고정한다.
- repair loop를 자동화하여 통과본만 simulation queue에 넣는다.

## 2) 실행 플로우 (강제 순서)
1. Alpha Maker 출력 수신
2. 파서 실패 시 포맷 복구 단계 우선 실행(JSON 구조만 복구)
3. `StaticValidator` 실행
4. 실패 시 repair instruction 생성
5. 동일 오류 반복 시 retrieval 확장 분기 실행
6. 수정본 재생성
7. 재검증
8. 통과본만 `simulate-candidates`로 전달
9. 결과를 evaluator/feedback으로 연결

## 3) 구현 범위
### 3.1 validator gate
- 신규(권장): `src/brain_agent/generation/validation_gate.py`
- 기능:
  - CandidateAlpha 검증
  - 오류 코드 분류
  - repair 프롬프트 생성

### 3.2 repair loop orchestrator
- 신규/수정:
  - `src/brain_agent/agents/llm_orchestrator.py` 또는 `src/brain_agent/agents/pipeline.py`
- 설정:
  - `max_repair_attempts` (권장 3~5)
  - `stop_on_repeated_error`

### 3.3 queue 진입 정책
- `validation_passed == true`인 후보만 시뮬 큐에 enqueue
- 실패본은 이유/시도 횟수와 함께 로그 저장
- exploit/explore lane 태그를 큐 메타에 보존한다

## 4) repair 규칙 (최소)
1. Unknown operator/field
- retrieval pack 후보 내 치환 우선
- 동일 오류 반복 시 확장된 retrieval pack 후보로 재시도

2. scope 위반
- REGULAR scope operator로 교체

3. 타입 위반
- ts_/group_/vec_ 규칙에 맞춰 필드/연산자 재배치

4. 빈 인자/괄호 오류
- 구조 재생성 요청 (포맷 복구 전용 프롬프트 우선)

## 5) 검증 커맨드 (완료 기준)
예시:
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-validation-loop \
  --idea /tmp/idea_out.json \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index \
  --max-repair-attempts 3 \
  --output /tmp/validated_candidates.json
```

검증 항목:
1. 검증 실패 후보가 시뮬 단계로 가지 않는다.
2. repair 재시도 후 통과본은 시뮬 단계로 전달된다.
3. 시도 횟수/오류 유형 로그가 남는다.
4. 루프 종료 조건(성공/포기)이 명확하다.
5. parse 실패 시 포맷 복구 단계가 먼저 실행된다.
6. 동일 오류 반복 시 retrieval 확장 분기가 실행된다.

## 6) 완료 정의 (Definition of Done)
- [ ] validation-first gate가 기본 경로로 적용
- [ ] repair loop 자동화 완료
- [ ] 시뮬 큐 진입 조건이 코드로 강제됨
- [ ] 재시도당 통과율 지표를 수집/조회 가능
- [ ] 포맷 복구 우선 정책이 구현됨
- [ ] 반복 오류에서 확장 분기로 탈출 가능함

## 7) step-21 이후 권장 작업
- diversity 점수까지 결합한 제출 후보 우선순위 계산
- 장기적으로는 운영 대시보드(비용/통과율/중복률) 자동화
