# Step 14 실행 산출물

## 목적
MVP/Production v1 Done Definition 항목을 실제 코드 산출물에 매핑해 완료 상태를 고정한다.

## MVP 구현 매핑
- BrainAPISession ensure_login: `src/brain_agent/brain_api/client.py`
- simulate_one: `src/brain_agent/brain_api/simulations.py`, `src/brain_agent/simulation/runner.py`
- recordsets fetch: `src/brain_agent/brain_api/simulations.py`
- operators/data-fields fetch: `src/brain_agent/brain_api/metadata.py`
- SQLite 저장: `src/brain_agent/storage/sqlite_store.py`
- evaluator top-N: `src/brain_agent/evaluation/evaluator.py`

## Production v1 구현 매핑
- OPTIONS settings validator: `src/brain_agent/validation/settings_validator.py`
- retrieval subset 구성: `src/brain_agent/retrieval/keyword.py`
- FastExpr Builder prompt + JSON 강제: `src/brain_agent/generation/prompting.py`
- 정적검증: `src/brain_agent/validation/static_validator.py`
- 피드백 루프: `src/brain_agent/feedback/mutator.py`
- 상관중복 제거: `src/brain_agent/evaluation/evaluator.py`
- 스케줄링/리포트: `scripts/cron_pipeline.sh`, `scripts/report_db_counts.sh`, `src/brain_agent/cli.py`
- 옵션 submit 모듈: `src/brain_agent/brain_api/submit.py`

## Step 15+ 인계 메모
- 운영 단계에서 실패율/통과율/중복률 KPI를 주간 단위로 추적한다.
