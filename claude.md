# Brain Alpha Generator

WorldQuant BRAIN API 기반 알파 리서치/시뮬레이션 자동화 시스템.
FastExpr 메타데이터(operators/datasets/data-fields)를 동기화하고, 멀티 에이전트 파이프라인으로 고품질 알파를 생산한다.

## 프로젝트 구조

```
src/brain_agent/           # Python 백엔드 (메인 패키지)
├── brain_api/             # BRAIN API 클라이언트 (인증, 세션, diversity)
├── agents/                # 오케스트레이터 (pipeline, llm_orchestrator, validation_loop)
├── metadata/              # 메타데이터 동기화 (operators/datasets/data-fields)
├── retrieval/             # Top-K retrieval pack 빌더 (BM25)
├── generation/            # knowledge pack, prompting, openai_provider, budget, validation_gate
├── validation/            # FastExpr 정적 검증기 (static_validator)
├── simulation/            # 시뮬레이션 러너 (POST /simulations + polling)
├── evaluation/            # 평가기 (Sharpe/fitness/turnover 기반)
├── feedback/              # 피드백 변이기 (파라미터 탐색 + 표현식 변형)
├── runtime/               # 이벤트 버스 (EventBus)
├── server/                # FastAPI 서버 (WebSocket 브리지, 제어 API)
├── storage/               # SQLite 저장소 (MetadataStore)
├── cli.py                 # CLI 진입점 (argparse)
├── config.py              # AppConfig (경로/설정)
├── schemas.py             # Pydantic 스키마 (IdeaSpec, CandidateAlpha, AlphaResult 등)
├── constants.py           # 상수
├── exceptions.py          # 커스텀 예외 (ManualActionRequired 등)
└── utils/                 # 유틸리티

frontend-next/             # Next.js 14 프론트엔드 (Neural Reactor HUD)
├── src/                   # React 18 + TypeScript + Tailwind CSS
├── package.json           # next 14.2.5, react-three/fiber, recharts, reactflow
└── tailwind.config.ts

configs/                   # JSON 설정 파일 (retrieval_budget, llm_budget, pipeline 등)
scripts/                   # 셸 스크립트 (sync_options, sync_metadata, simulate 등)
docs/                      # 문서 (steps, rules, artifacts, baseguideline)
architecture/              # 워크플로 맵
```

## 기술 스택

- **백엔드**: Python 3.11+, FastAPI, uvicorn, pydantic v2, requests, pandas, tenacity, rich, openai SDK, rank-bm25
- **프론트엔드**: Next.js 14, React 18, TypeScript, Tailwind CSS, Three.js (react-three/fiber), Recharts, ReactFlow
- **저장소**: SQLite (`data/brain_agent.db`), JSON 파일 기반 인덱스
- **LLM**: OpenAI API (gpt-5.2 기본, `--llm-provider mock`으로 API 없이 계약 검증 가능)

## 개발 환경 설정

```bash
# Python 가상환경
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 크리덴셜 (.env 또는 ~/.brain_credentials)
cp .env.example .env
# BRAIN_CREDENTIAL_EMAIL / BRAIN_CREDENTIAL_PASSWORD 입력
# OpenAI 사용 시 OPENAI_API_KEY 입력

# 프론트엔드
cd frontend-next && npm install && npm run dev
```

## CLI 명령 (PYTHONPATH=src)

| 명령 | 설명 |
|------|------|
| `sync-options` | OPTIONS /simulations 동기화 |
| `sync-metadata` | operators/datasets/data-fields 동기화 |
| `validate-expression <expr>` | FastExpr 정적 검증 |
| `build-retrieval-pack` | Top-K retrieval pack 빌드 |
| `build-knowledge-pack` | FastExpr knowledge pack 빌드 |
| `run-idea-agent` | Idea Researcher 에이전트 실행 |
| `run-alpha-maker` | Alpha Maker 에이전트 실행 |
| `run-validation-loop` | Validation-first 생성/수리 루프 |
| `estimate-prompt-cost` | LLM 예산 추정 |
| `simulate-candidates` | 시뮬레이션 실행 |
| `evaluate-results` | 결과 평가 |
| `serve-live-events` | FastAPI WebSocket 서버 실행 |

모든 CLI는 `PYTHONPATH=src python3 -m brain_agent.cli <command>` 형태로 실행한다.

## 코딩 컨벤션

- Python 소스는 `src/brain_agent/` 하위에 모듈별로 배치
- 스키마/데이터 모델은 `pydantic.BaseModel` 사용 (v2 스타일: `model_validate`, `model_dump_json`)
- 설정은 `configs/*.json`으로 분리, 코드에서 하드코딩 금지
- 이벤트 로깅은 `EventBus.publish()` 통해 SQLite `event_log` 테이블에 기록
- CLI 출력은 JSON 형태로 통일 (`json.dumps` → stdout)
- 환경변수 우선순위: `.env` → `BRAIN_*` 환경변수 → `~/.brain_credentials`
- `from __future__ import annotations` 사용
- import 스타일: 표준라이브러리 → 서드파티 → 로컬 (상대 import `.` 사용)

## 핵심 파이프라인 흐름

```
Metadata Sync → Retrieval Pack → Knowledge Pack → Idea Agent → Alpha Maker
  → Static Validator → Budget Gate → Simulation → Evaluator → Feedback Mutator → (반복)
```

## 작업 원칙

- `docs/steps/README.md`에서 현재 목표 step을 먼저 확인
- `docs/baseguideline.md`의 정책 준수/파이프라인 분리 원칙을 전제로 작업
- 요청받지 않은 step은 수행하지 않음
- 코드 변경이 없는 업무도 `docs/non-coding-tasks.md`에 기록
- ToS/정책 위반 가능성이 있는 수집/자동화를 임의로 추가하지 않음
- 플랫폼용 지표와 실거래 가능성을 동일 근거로 혼합 보고하지 않음

## 참고 문서

- `docs/baseguideline.md`: 통합 가이드 (운영 원칙, API 설계, 에이전트 아키텍처)
- `docs/rules/`: FastExpr 오퍼레이터/필드 타입/알파 제작 규칙집
- `docs/steps/`: 단계별 구현 체크리스트
- `architecture/current-workflow-map.md`: 현재 워크플로 맵 (mermaid)
- `agent.md`: 다음 작업자용 메타 프롬프트
