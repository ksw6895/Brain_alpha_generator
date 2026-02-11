# Brain Alpha Generator

WorldQuant BRAIN API 기반 알파 리서치/시뮬레이션 자동화 코드베이스입니다.

## 빠른 시작

1. 가상환경 구성
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2. 크리덴셜 설정 (권장: `.env`)
```bash
cp .env.example .env
# .env 파일에 BRAIN_CREDENTIAL_EMAIL / BRAIN_CREDENTIAL_PASSWORD 입력
# step-19 OpenAI 실행 시 OPENAI_API_KEY도 함께 입력
```

3. (대안) 홈 디렉토리 크리덴셜 파일 생성
```bash
bash scripts/setup_credentials.sh
```

4. 시뮬레이션 옵션 동기화
```bash
PYTHONPATH=src bash scripts/sync_options.sh
```

5. 메타데이터 동기화
```bash
PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000
```

6. Top-K retrieval pack 생성 (step-17)
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/retrieval_pack.json
```

7. FastExpr knowledge pack 생성 (step-18)
```bash
PYTHONPATH=src python3 -m brain_agent.cli build-knowledge-pack \
  --output-dir data/meta/index
```

8. 2-agent 계약 실행 (step-19)
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-idea-agent \
  --llm-provider openai \
  --llm-model gpt-5.2 \
  --reasoning-effort medium \
  --verbosity medium \
  --reasoning-summary auto \
  --input docs/artifacts/step-08/ideaspec.example.json \
  --output /tmp/idea_out.json

PYTHONPATH=src python3 -m brain_agent.cli build-retrieval-pack \
  --idea /tmp/idea_out.json \
  --output /tmp/retrieval_pack.json

PYTHONPATH=src python3 -m brain_agent.cli run-alpha-maker \
  --llm-provider openai \
  --llm-model gpt-5.2 \
  --reasoning-effort medium \
  --verbosity medium \
  --reasoning-summary auto \
  --idea /tmp/idea_out.json \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index \
  --output /tmp/candidate_alpha.json
```

OpenAI 키를 아직 넣지 않았거나 API 호출 없이 계약만 검증하려면 `--llm-provider mock`을 사용합니다.

9. step-20 예산 추정/폴백 점검
```bash
PYTHONPATH=src python3 -m brain_agent.cli estimate-prompt-cost \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index \
  --llm-budget-config configs/llm_budget.json \
  --output /tmp/budget_estimate.json
```

10. (선택) 실시간 이벤트 WebSocket 브리지 서버 실행
```bash
PYTHONPATH=src python3 -m brain_agent.cli serve-live-events --host 127.0.0.1 --port 8765
```

예산/품질 조회 API:
- `GET /api/runs/{run_id}/budget`
- `GET /api/runs/{run_id}/kpi`
- `GET /api/runs/{run_id}/validation_kpi`
- `GET /api/runs/{run_id}/reactor_status`

웹 명령 콘솔 API(프론트에서 실행 제어):
- `GET /api/control/actions` (허용된 액션/템플릿 조회)
- `POST /api/control/jobs` (액션 실행 요청)
- `GET /api/control/jobs/{job_id}` (작업 상태/결과 조회)
- `GET /api/control/jobs` (최근 작업 목록)

Reactor HUD(로컬 프로토타입) 열기:
- 서버 실행 후 `http://127.0.0.1:8765/ui/reactor?run_id=<RUN_ID>`

Step-21 Validation-first loop 실행:
```bash
PYTHONPATH=src python3 -m brain_agent.cli run-validation-loop \
  --llm-provider openai \
  --idea /tmp/idea_out.json \
  --retrieval-pack /tmp/retrieval_pack.json \
  --knowledge-pack-dir data/meta/index \
  --max-repair-attempts 3 \
  --output /tmp/validated_candidates.json
```

Neural Genesis Lab(로컬 프로토타입) 열기:
- 서버 실행 후 `http://127.0.0.1:8765/ui/neural-lab?run_id=<RUN_ID>`
- 상단 `Command Console`에서 액션을 선택해 웹에서 바로 실행 가능
- 기본 권장: `run-quick-validation-loop` (idea -> retrieval -> validation-loop를 1회 실행)
- `Auto Stream Run`을 켜면 완료된 run_id를 자동으로 붙여 스트리밍 연결

Next.js Neural Reactor HUD(신규 프론트) 실행:
```bash
# 터미널 A (백엔드)
BRAIN_UI_ORIGINS=http://127.0.0.1:3000,http://localhost:3000 \
PYTHONPATH=src python3 -m brain_agent.cli serve-live-events --host 127.0.0.1 --port 8765

# 터미널 B (프론트)
cd frontend-next
cp env.local.example .env.local
npm install
npm run dev
```
- 브라우저: `http://127.0.0.1:3000`
- 프론트 `Command Console`에서 `/api/control/jobs`를 호출해 아이디어/알파/validation-loop를 실행
- 실시간 이벤트는 `/ws/live`를 사용해 스트리밍

> biometrics 인증이 필요한 계정이면 위 스크립트가 URL을 안내하고 터미널에서 대기합니다.
> 브라우저에서 인증 완료 후 Enter를 누르면 진행됩니다.
> 세션 쿠키(`~/.brain_session_cookies`)를 재사용하므로 연속 실행 시 재인증이 줄어듭니다.
> 참고로 `sync_metadata.sh`는 내부적으로 options 동기화도 함께 수행합니다.
> 즉, 보통은 `sync_metadata.sh` 한 번만 실행해도 됩니다.
> 기본값으로 `/data-fields`는 전체 dataset id를 순회하는 샤딩 수집으로 동기화합니다.
> (전역 `/data-fields` 조회는 API count 상한으로 약 10,000에서 잘릴 수 있어 기본 전략에서 제외했습니다.)
> 429를 만나면 대기 후 자동 재개하며, 반복 429 구간에서는 대기 시간이 점진적으로 커집니다.

전체 동기화가 너무 오래 걸리면 범위를 줄여 실행할 수 있습니다:
```bash
BRAIN_MAX_FIELD_DATASETS=10 PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000
```
위처럼 `BRAIN_MAX_FIELD_DATASETS`를 지정하면 전체가 아니라 선택된 일부 dataset 기준으로만 `/data-fields`를 수집합니다.

필드까지 당장 필요 없으면:
```bash
PYTHONPATH=src python3 -m brain_agent.cli sync-metadata --interactive-login --skip-fields --region USA --delay 1 --universe TOP3000
```

429에서 즉시 실패하도록 바꾸려면:
```bash
BRAIN_WAIT_ON_RATE_LIMIT=0 PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000
```

## 메타데이터 인덱스 산출물

`sync_metadata.sh` 실행 후 아래 인덱스가 자동 생성됩니다.
- `data/meta/index/category_glossary.json`: 카테고리 의미 + 에이전트 힌트
- `data/meta/index/datasets_by_category.json`
- `data/meta/index/datasets_by_subcategory.json`
- `data/meta/index/operators_by_category.json`
- `data/meta/index/manifest.json`
- `data/meta/by_category/*.datasets.json` (카테고리별 dataset 분할 파일)
- `data/meta/by_subcategory/*.datasets.json` (서브카테고리별 dataset 분할 파일)
- `data/meta/by_category/*.fields.json` (필드 수집 시 카테고리별 field 분할 파일)
- `data/meta/by_subcategory/*.fields.json` (필드 수집 시 서브카테고리별 field 분할 파일)
- `data/meta/data_fields_<REGION>_<DELAY>_<UNIVERSE>_progress.json` (필드 수집 진행 상태 체크포인트)

## 인증 우선순위

CLI 실행 시 자격증명은 아래 순서로 로드됩니다.
1. 환경변수: `BRAIN_CREDENTIAL_EMAIL`, `BRAIN_CREDENTIAL_PASSWORD` (`.env` 포함)
2. 호환 환경변수: `BRAIN_EMAIL`, `BRAIN_PASSWORD`
3. 파일: `~/.brain_credentials` (또는 `--credentials`로 지정한 경로)

비대화형 실행(예: cron)에서 biometrics 대기를 비활성화하려면:
```bash
BRAIN_INTERACTIVE_LOGIN=0 PYTHONPATH=src bash scripts/sync_options.sh
```

## 주요 경로

- API 클라이언트: `src/brain_agent/brain_api/client.py`
- 메타데이터 동기화: `src/brain_agent/metadata/sync.py`
- retrieval pack 빌더: `src/brain_agent/retrieval/pack_builder.py`
- knowledge pack 빌더: `src/brain_agent/generation/knowledge_pack.py`
- 정적 검증기: `src/brain_agent/validation/static_validator.py`
- 시뮬레이션 러너: `src/brain_agent/simulation/runner.py`
- 평가기: `src/brain_agent/evaluation/evaluator.py`
- 피드백 변이기: `src/brain_agent/feedback/mutator.py`
- 파이프라인 오케스트레이터: `src/brain_agent/agents/pipeline.py`
- validation gate: `src/brain_agent/generation/validation_gate.py`
- validation loop 오케스트레이터: `src/brain_agent/agents/validation_loop.py`
- CLI 진입점: `src/brain_agent/cli.py`
- retrieval budget 설정: `configs/retrieval_budget.json`
- llm budget 설정: `configs/llm_budget.json`

## 샘플 Fixture

- API 응답 샘플(JSON): `docs/artifacts/fixtures/`
- 예시 목적이며, 운영 시에는 실제 API fetch 결과를 사용하세요.

## 주의

- 실제 로그인/바이오메트릭 인증은 사용자 수동 개입이 필요할 수 있습니다.
- submit endpoint는 계정 권한/정책에 따라 동작이 다를 수 있어 옵션으로 분리했습니다.
