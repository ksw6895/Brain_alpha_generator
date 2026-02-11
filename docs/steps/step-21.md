# Step 21

## Validation-first 생성/수정 루프 완성

## 상태 (2026-02-12)
- 구현 완료
- 구현 보고서: `docs/artifacts/step-21/implementation_report.md`

## 0) 이 문서만 읽은 신규 에이전트용 요약
- step-21은 "LLM 생성 결과를 바로 시뮬에 보내지 않도록" 파이프라인을 완성하는 단계다.
- 생성 -> 정적검증 -> 수정 -> 재검증 -> 시뮬 순서를 강제해야 한다.
- 목표는 시뮬 실패율 감소와 고비용 재시도 감소다.
- 단, 반복 실패에서 같은 후보만 맴돌지 않도록 포맷 복구/검색 확장 분기를 함께 둔다.
- 이 step에서 검증/수정/시뮬/평가 이벤트를 완성해 "Arena + Evolutionary Tree" UI를 실시간 구동한다.

## 1) 배경과 의도
### 1.1 현재 문제
- 생성된 CandidateAlpha를 즉시 시뮬하면 문법/타입/스코프 오류로 실패한다.
- 실패 시 API 호출 비용과 시간이 낭비된다.

### 1.2 목표
- validation-first gate를 표준 경로로 고정한다.
- repair loop를 자동화하여 통과본만 simulation queue에 넣는다.
- 변이 계보(parent -> child)와 백테스트 진행 상태를 이벤트로 기록한다.

### 1.3 실측 백테스트 응답 기반 설계 원칙
- Arena/Evolutionary UI를 구현하기 전에 실제 백테스트 응답(JSON)과 이벤트 타임라인을 먼저 확보한다.
- 예시 알파를 실제로 시뮬레이션하고 완료까지 기다린 다음, 응답 필드/진행률 패턴/지연시간 분포를 분석해 프론트 이벤트 계약을 고정한다.
- 즉, step-21의 시각화는 mock payload가 아니라 실제 응답을 기준으로 설계한다.

실측 관측(2026-02-11 UTC, alpha_id=`j2l8Vzv9`, `O0w8RPJd`):
- 실제 저장 이벤트는 현재 코드에서 `simulation.completed`(dotted) + alias `simulation_completed`(underscore) 둘 다 기록된다.
- metrics payload 예시:
  - `sharpe=-0.64` (rerun: `-0.63`)
  - `fitness=-0.35`
  - `turnover=0.1913` (rerun: `0.1856`)
  - `drawdown=0.6091` (rerun: `0.6017`)
  - `coverage=null` (null 가능)
- 계정/권한에 따라 `/alphas/{id}/recordsets`가 2xx + non-JSON(빈 본문)으로 내려올 수 있다.
- 정식 저장 파일(`data/probes/step20/alpha_result_probe_rerun.json`) 기준으로는 `raw_payload.is/train/test/checks`가 포함되므로,
  Arena/Evaluator UI는 초기 버전에서 `raw_payload.is` 중심으로 매핑하고 `train/test`는 확장 탭으로 분리하는 것이 안전하다.

따라서 step-21의 Arena 실시간성 계약은 아래처럼 현실적으로 잡는다.
1. 1차 필수: `simulation.enqueued|simulation.started|simulation_completed` 단계 이벤트
2. 2차 선택: recordset 기반 PnL 스트리밍(가능 계정에서만)
3. recordset 미지원/지연 시에도 `simulation_completed.metrics` 기반 요약 HUD는 반드시 표시

권장 사전 수집:
1. 예시 알파 제출 후 `simulation_completed`(또는 alias `simulation.completed`) payload 원문 확보
2. `evaluation.completed` 직후 scorecard 필드 매핑 확인
3. parent-child mutation 이벤트와 시간축 정렬 가능 여부 확인

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
  - `src/brain_agent/agents/validation_loop.py`
  - `src/brain_agent/cli.py` (`run-validation-loop`)
- 설정:
  - `max_repair_attempts` (권장 3~5)
  - `stop_on_repeated_error`

### 3.3 queue 진입 정책
- `validation_passed == true`인 후보만 시뮬 큐에 enqueue
- 실패본은 이유/시도 횟수와 함께 로그 저장
- exploit/explore lane 태그를 큐 메타에 보존한다

### 3.4 프론트 동시 적용 범위 (F21: Neural Genesis Lab)
- 컨셉: `Living Neural Network`
- 정적인 트리가 아니라, 아이디어의 탄생/수정/사멸을 우주(Galaxy)처럼 표현한다.
- 로컬 프로토타입: `docs/artifacts/step-21/neural_genesis_lab.html` (`/ui/neural-lab`)

#### 3.4.1 Data Synapse Map (마인드맵 수색 시각화)
- 구현: `react-force-graph-3d`
- 동작:
  - 화면 중앙에 `Brain Core`(대형 3D 구체)를 배치
  - 에이전트가 `Open`, `Close`, `Volume` 등 데이터 필드를 검토하면 해당 노드가 발광하고 코어와 레이저 링크로 연결
  - `Data Searching...` 단계에서 다수 노드를 스캔하는 빔 이펙트 표시
  - 미사용 노드는 dimmed, 채택 노드는 네온 컬러 활성화

#### 3.4.2 Evolutionary Galaxy (변이 계보도)
- 구현: `React Three Fiber + Particle System`
- 동작:
  - 각 `CandidateAlpha`를 우주 공간의 별(Star)로 시각화
  - Parent -> Child: 부모 별에서 혜성 꼬리 형태로 자식 별 탄생 애니메이션
  - Validation 상태:
    - Passed: 청록/초록 안정 발광
    - Failed: 붉은 폭발 후 잿빛 잔해로 전환
    - Repair Loop: 별 주변에 수리 드론 파티클 회전, 성공 시 재점등

#### 3.4.3 Arena Spectator (백테스트 실시간 중계)
- 구현: `Visx` 또는 Custom WebGL Shader Line
- 동작:
  - 레이싱 HUD 스타일의 PnL 실시간 라인 렌더링
  - 수익 구간은 금빛 파티클, 손실 구간은 붉은 비네팅 경고
  - 하단 터미널에 `LOG: Alpha #402 execution... Sharpe Ratio calculating...` 스트림 출력

#### 3.4.4 권장 시각 언어
- Color: `#050505`(Deep Space Black), `#00f3ff`(Neon Cyan), `#0aff00`(Matrix Green), `#ff0055`(Alert Red)
- Typography: `JetBrains Mono` 또는 `Orbitron`
- Motion: `Framer Motion + AnimatePresence`, 수치 변경은 CountUp 애니메이션 적용

### 3.5 코드 연결 포인트 (현재 구현 기준)
아래 파일은 이미 동작 중인 경로이므로, 이벤트 삽입 시 우선 수정 대상으로 본다.
1. `src/brain_agent/simulation/runner.py`
- 기존 `simulation_completed`, `simulation_skipped_duplicate` 이벤트가 이미 저장된다.
- step-21에서 `simulation.started`, `simulation.enqueued`를 추가한다.
2. `src/brain_agent/feedback/mutator.py`
- 변이 생성 시 parent-child 관계를 payload로 저장해 계보 그래프를 만든다.
3. `src/brain_agent/evaluation/evaluator.py`
- scorecard 계산 직후 `evaluation.completed` 이벤트를 기록한다.
4. `src/brain_agent/brain_api/simulations.py`
- `poll_simulation()`에 progress callback 훅을 넣어 Arena 진행률 이벤트를 송출한다.
- 단, 실 API에서 중간 진행률 필드가 안정적으로 내려오지 않는 경우가 있어 callback은 "있으면 활용, 없으면 단계 이벤트만" 전략으로 구현한다.
5. `src/brain_agent/server/app.py`
- `GET /api/runs/{run_id}/validation_kpi`로 재시도당 통과율(pass/fail per attempt)을 조회한다.

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

## 4.1 이벤트 순서 계약 (강제)
1. `agent.alpha_generated`
2. `validation.started`
3. `validation.failed` 또는 `validation.passed`
4. 실패 시 `validation.retry_started` -> `validation.retry_failed|validation.retry_passed`
5. 통과 시 `simulation.enqueued` -> `simulation.started` -> `simulation.completed`
6. 마지막 `evaluation.completed`

순서 위반 이벤트가 발생하면 로그에는 남기되, run summary에 `event_order_violation=true`를 기록한다.

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
7. Arena 이벤트(`simulation.*`, `evaluation.completed`)가 시간순으로 조회된다.
8. mutation 이벤트로 parent-child 계보 그래프를 재구성할 수 있다.

## 6) 완료 정의 (Definition of Done)
- [x] validation-first gate가 기본 경로로 적용
- [x] repair loop 자동화 완료
- [x] 시뮬 큐 진입 조건이 코드로 강제됨
- [x] 재시도당 통과율 지표를 수집/조회 가능
- [x] 포맷 복구 우선 정책이 구현됨
- [x] 반복 오류에서 확장 분기로 탈출 가능함
- [x] Arena(백테스트) 실시간 이벤트 계약이 고정됨
- [x] Evolutionary Tree(변이 계보) 재구성 가능한 이벤트가 저장됨

## 7) step-21 이후 권장 작업
- diversity 점수까지 결합한 제출 후보 우선순위 계산
- 장기적으로는 운영 대시보드(비용/통과율/중복률) 자동화
