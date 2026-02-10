# Step 14

## 구현 체크리스트 (코드 에이전트용 “Done Definition”)


### 14.1 MVP (1~2일 목표)

* [ ] BrainAPISession: ensure_login 구현(기본 auth + 204/200 처리)
* [ ] simulate_one(expression, settings) 구현(/simulations → poll → /alphas/{id})
* [ ] recordsets fetch 구현(/alphas/{id}/recordsets + /recordsets/<name>)
* [ ] operators fetch 구현(/operators 저장)
* [ ] data-fields fetch 구현(/data-fields: dataset.id, limit/offset 페이지네이션)
* [ ] SQLite 저장(operators/data_fields/alphas_results)
* [ ] 간단 evaluator(sharpe/turnover/fitness) + top-N 출력

### 14.2 Production v1 (1~2주 목표)

* [ ] OPTIONS /simulations 기반 settings validator
* [ ] retrieval(키워드 기반)로 operator/field subset 구성
* [ ] FastExpr Builder LLM 프롬프트 + JSON output 강제
* [ ] 정적검증(토큰/괄호/존재성/스코프/최소 타입)
* [ ] 피드백 루프(파라미터 탐색 + 변형)
* [ ] 상관 기반 중복 제거(daily-pnl correlation)
* [ ] 스케줄링(cron) + 로그/대시보드(간단 CLI 리포트)
* [ ] (옵션) submit 모듈을 플래그로 분리하여 안전하게 실험

---


## 체크리스트
- [ ] MVP (1~2일 목표)
- [ ] Production v1 (1~2주 목표)
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
