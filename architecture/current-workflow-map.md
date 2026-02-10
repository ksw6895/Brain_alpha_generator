# Current Workflow Map

이 문서는 "지금 실제로 돌아가는 흐름"과 "아직 연결/구현이 남은 흐름"을 분리해 설명합니다.  
대상 독자: 사용자(실행 관점) + 개발자(구조/연결 관점).

## 1) 구현된 작업 흐름 (실행 가능)

아래 플로우는 현재 저장소에서 실제로 실행 가능한 경로입니다.

- 사용자 입력이 필요한 지점:
  - `scripts/setup_credentials.sh` 실행 시 계정 입력
  - 계정 정책에 따라 biometrics 인증이 필요할 수 있음
- 그 외는 스크립트/CLI로 자동 처리됨
- 핵심 저장 위치:
  - 메타데이터: `data/meta/*`
  - 로컬 DB: `data/brain_agent.db`
  - 시뮬 결과/레코드셋: `data/simulation_results/*`, `data/recordsets/*`

```mermaid
flowchart TD
  U["\"사용자\"가 실행 시작"] --> ENV["\"환경 준비\": .venv + requirements 설치"]
  ENV --> CRED["\"크리덴셜 저장\": scripts/setup_credentials.sh"]
  CRED --> CREDFILE["\"~/.brain_credentials\" 생성 (권한 600)"]

  CREDFILE --> OPT["\"옵션 동기화\": scripts/sync_options.sh"]
  OPT --> OPTSAVE["\"OPTIONS /simulations\" 저장 -> data/meta + SQLite"]

  OPTSAVE --> META["\"메타 동기화\": scripts/sync_metadata.sh"]
  META --> METASAVE["\"/operators\", \"/data-sets\", \"/data-fields\" 저장"]

  METASAVE --> CAND["\"후보 알파 준비\": JSON 파일(수동/템플릿)"]
  CAND --> VAL["\"정적 검증\": scripts/validate_expression.sh"]
  VAL --> SIM["\"시뮬 실행\": scripts/simulate_candidates.sh"]

  SIM --> DEDUP["\"중복 검사\": fingerprint 비교 후 스킵/진행"]
  DEDUP --> POSTSIM["\"POST /simulations\" + \"Retry-After\" 폴링"]
  POSTSIM --> ALPHA["\"alpha_id\" 및 상세/recordsets 수집"]

  ALPHA --> EVAL["\"평가/랭킹\": scripts/evaluate_results.sh"]
  EVAL --> SCORE["\"ScoreCard\" 생성 (Sharpe/Fitness/Turnover/상관)"]

  SCORE --> DIVOPT["\"선택\": scripts/diversity_snapshot.sh"]
  DIVOPT --> OUT["\"운영 출력\": 통과 후보/로그/DB 누적"]
```

### 구현된 흐름에서 사용자가 체감하는 실행 순서

1. `bash scripts/setup_credentials.sh`  
2. `PYTHONPATH=src bash scripts/sync_options.sh`  
3. `PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000`  
4. 후보 JSON 준비 후 `PYTHONPATH=src bash scripts/simulate_candidates.sh <input.json>`  
5. `PYTHONPATH=src bash scripts/evaluate_results.sh <result.json>`

---

## 2) 미구현/부분구현 작업 흐름 (현재는 완전 자동 아님)

아래 플로우는 "모듈은 있거나 설계는 되어 있지만", 완전 자동 E2E로는 아직 미연결/미완성인 부분입니다.

- 아이디어 수집 -> LLM 생성 -> retrieval 결합 -> 자동 재작성 루프: 부분구현
- 피드백 변이 결과를 자동으로 다음 시뮬 배치에 지속 연결: 부분구현
- 제출 전 정책 게이트 + 자동 submit 운영: 옵션 모듈만 존재
- 운영 대시보드/모니터링 자동화: 최소 스크립트 수준, 제품 수준 대시보드는 미구현

```mermaid
flowchart TD
  I0["\"미구현 시작점\": 완전 자동 알파 생산 루프"] --> I1["\"Idea Collector (LLM)\" 자동 아이디어 생성"]
  I1 --> I2["\"Retrieval 결합\": operators/fields Top-K 자동 주입"]
  I2 --> I3["\"FastExpr Builder (LLM)\" JSON 강제 출력"]

  I3 --> I4["\"Static Validator\" 통과 여부 판단"]
  I4 -->|"\"실패\""| I5["\"자동 Rewrite 루프\" (에러 피드백 반영)"]
  I5 --> I3

  I4 -->|"\"통과\""| I6["\"Multi-Simulation Batch\" 자동 편성/실행"]
  I6 --> I7["\"Evaluator\" 점수/상관/안정성 평가"]
  I7 --> I8["\"Feedback Mutator\" 변이 생성"]
  I8 --> I6

  I7 --> I9["\"Submit Gate\" 정책/중복/다양성 체크"]
  I9 --> I10["\"Submit API\" 자동 제출 + 상태 추적"]
  I10 --> I11["\"운영 대시보드\" KPI/알림/리포트"]
```

### 미구현/부분구현 포인트 요약

- `src/brain_agent/generation/prompting.py`는 "프롬프트/파서"만 있고, 실제 LLM 호출 오케스트레이션이 아직 없음
- `src/brain_agent/agents/pipeline.py`는 파이프라인 뼈대이며, 현재 빌더는 안전 템플릿 중심
- `src/brain_agent/brain_api/submit.py`는 옵션 래퍼이며, 운영 게이트와 완전 자동 submit 플로우는 미연결
- `scripts/cron_pipeline.sh`는 최소 스케줄 샘플이며, 장애복구/알림/관측성은 확장 필요

---

## 3) 상태 한 줄 정리

- "시뮬레이션 엔진 + 평가 엔진"은 실행 가능한 상태
- "완전 자동 후보 생성/학습형 루프/제출 운영"은 다음 구현 단계
