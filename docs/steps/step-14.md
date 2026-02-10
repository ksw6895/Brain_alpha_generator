# Step 14

## 구현 체크리스트 (코드 에이전트용 “Done Definition”)


### 14.1 MVP (1~2일 목표)

* [x] BrainAPISession: ensure_login 구현(기본 auth + 204/200 처리)
* [x] simulate_one(expression, settings) 구현(/simulations → poll → /alphas/{id})
* [x] recordsets fetch 구현(/alphas/{id}/recordsets + /recordsets/<name>)
* [x] operators fetch 구현(/operators 저장)
* [x] data-fields fetch 구현(/data-fields: dataset.id, limit/offset 페이지네이션)
* [x] SQLite 저장(operators/data_fields/alphas_results)
* [x] 간단 evaluator(sharpe/turnover/fitness) + top-N 출력

### 14.2 Production v1 (1~2주 목표)

* [x] OPTIONS /simulations 기반 settings validator
* [x] retrieval(키워드 기반)로 operator/field subset 구성
* [x] FastExpr Builder LLM 프롬프트 + JSON output 강제
* [x] 정적검증(토큰/괄호/존재성/스코프/최소 타입)
* [x] 피드백 루프(파라미터 탐색 + 변형)
* [x] 상관 기반 중복 제거(daily-pnl correlation)
* [x] 스케줄링(cron) + 로그/대시보드(간단 CLI 리포트)
* [x] (옵션) submit 모듈을 플래그로 분리하여 안전하게 실험

---



## Step 14 실행 결과
- 산출물 문서: `docs/step-14-execution.md`
- 구현 산출물/완료 범위/의존성은 실행 문서에 정리.

## 체크리스트
- [x] MVP (1~2일 목표)
- [x] Production v1 (1~2주 목표)
- [x] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
