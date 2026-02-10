# Steps Roadmap (Active)

## 문서 목적
이 디렉토리는 "앞으로 구현할 작업"만 담는다.
이 문서 하나만 읽어도 신규 코드 에이전트가 프로젝트 방향을 이해하고 착수할 수 있어야 한다.

## 프로젝트 한 줄 목표
WorldQuant BRAIN용 FastExpr 알파를 LLM 기반 멀티 에이전트로 생성하되,
비용 폭증과 문법 오류를 막기 위해 Top-K retrieval + validation-first 루프를 강제한다.

## 현재 상태 (착수 시점 기준)
- 메타데이터 동기화 파이프라인은 이미 구현됨.
- operators/datasets/data-fields는 로컬 DB와 JSON 인덱스에 저장됨.
- 정적 검증기, 시뮬레이터, 평가기는 구현됨.
- 미완성 영역: LLM 오케스트레이션, 비용 제어, 생성-수정 자동 루프의 운영 완성도.

## 절대 원칙
1. 전체 metadata를 LLM prompt에 직접 넣지 않는다.
2. 아이디어별 Top-K subset만 LLM에 전달한다.
3. 정적검증 통과본만 시뮬레이션으로 보낸다.
4. 플랫폼용 파이프라인 결과와 실거래용 해석을 혼합하지 않는다.
5. 비용 절감만을 최적화하지 않는다. 탐색(explore) 예산을 별도로 유지한다.
6. 동일 오류 반복 시 축소만 하지 않고 retrieval 확장 경로를 반드시 제공한다.

## 권장 읽기 순서 (신규 에이전트)
1. `docs/baseguideline.md`
2. `architecture/current-workflow-map.md`
3. `docs/steps/README.md` (현재 문서)
4. 수행할 step 문서 (`step-17`부터 순차)

## Active Steps
- `docs/steps/step-17.md`: LLM 컨텍스트 게이팅 + Top-K retrieval 강제
- `docs/steps/step-18.md`: FastExpr 지식팩 구축(API + 실전 예시)
- `docs/steps/step-19.md`: 2-Agent 계약 설계(Idea Researcher / Alpha Maker)
- `docs/steps/step-20.md`: 토큰/비용 제어 레이어 및 retrieval budget 정책
- `docs/steps/step-21.md`: Validation-first 생성/수정 루프 + 시뮬/평가 연결

## 프론트엔드/관측성 병렬 트랙 (F-Track)
프론트엔드를 "마지막 장식"으로 미루지 않고, step-17부터 단계별 산출물 계약에 동시 반영한다.

### F-Track 목표
1. 사용자가 대기 중에도 에이전트 탐색/검증/시뮬 진행 상황을 실시간으로 본다.
2. 리서치 품질(coverage/novelty/diversity)과 운영 품질(실패율/비용/재시도)을 같은 화면에서 추적한다.
3. 시각화 요구 때문에 코어 로직 스키마가 흔들리지 않도록 step별 계약을 먼저 동결한다.

### 권장 기술 스택 (로컬 운영 기준)
- Frontend: `Next.js (React) + TypeScript`
- 실시간/상태 연출: `Framer Motion`
- 네트워크/마인드맵: `react-force-graph` (2D/3D)
- 3D 연출: `three.js` + `@react-three/fiber`
- 지표 차트: `Tremor` 또는 `Recharts`
- Backend API/stream: `FastAPI + WebSocket`

### 코드베이스 연동 원칙
1. 기존 `MetadataStore.append_event()` 기반 로그를 보존하면서 WebSocket 스트림으로 확장한다.
2. 이벤트 페이로드는 JSON 단일 포맷으로 고정하고, DB 저장 payload와 WS payload를 동일 스키마로 맞춘다.
3. 이벤트명은 도메인 prefix를 사용한다.
예: `retrieval.pack_built`, `agent.idea_started`, `validation.retry_failed`, `simulation.completed`.
기존 이벤트(`simulation_completed`, `simulation_skipped_duplicate`)는 마이그레이션 기간 동안 alias로 병행 유지한다.
4. 프론트 전용 데이터는 "원본 메타데이터 복제" 대신 "요약/인덱스/관계 그래프"로 제공한다.

### Step별 F-Track 반영 범위
- step-17: retrieval pack + mindmap 그래프 계약 + retrieval 이벤트 정의
- step-18: knowledge pack + 시각화용 요약팩(툴팁/에러 taxonomy) 생성
- step-19: 2-agent 실시간 스트림 계약 + "Brain Terminal" 이벤트 추가
- step-20: 비용/예산/fallback/novelty KPI를 계기판용 telemetry로 고정
- step-21: validation-first 루프 + 시뮬 진행 + 백테스트 Arena 리플레이 이벤트 완성

### UI 연출 가이드 (제품 톤)
1. Neural Cosmos
- retrieval 탐색 중 노드는 `searching` 상태(붉은 계열), 선정 노드는 `selected`(푸른 계열)로 고정한다.
- 노드 크기/밝기는 score 또는 사용 빈도 기반으로 산출한다.
2. Brain Terminal
- 단순 로그 dump 대신 `event_type`, `stage`, `severity`를 강조한 스트림 패널로 제공한다.
- parse 실패/복구/재시도는 연속 이벤트 블록으로 묶어 보여준다.
3. Arena
- 백테스트 지표(PnL/Sharpe/Fitness/Turnover)는 정적 카드가 아니라 run 진행과 함께 갱신한다.
4. Evolutionary Tree
- 후보 변이(parent->child)는 edge 중심으로 시각화하고, 폐기된 후보는 별도 상태(`candidate.dropped`)로 남긴다.

## 단계 의존성
- step-17 완료 후 step-18 착수
- step-18 완료 후 step-19 착수
- step-19 완료 후 step-20 착수
- step-20 완료 후 step-21 착수

## 작업 결과물 기준
각 step은 최소 아래를 남긴다.
1. 코드 변경 (필요 파일 명시)
2. 실행/검증 커맨드와 결과 요약
3. 실패 케이스와 재현 방법
4. 다음 step 진입 조건

## Retired
- 기존 완료 문서(`step-00~16`, `step-00~16-execution`)는 정리 후 제거됨.
- 제거 이력/사유: `docs/steps/retired-v1-steps.md`
