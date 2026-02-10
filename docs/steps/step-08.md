# Step 8

## 데이터 스키마 (파이프라인 안정화를 위한 최소 저장 구조)


### 8.1 IdeaSpec (LLM 출력 표준)

```json
{
  "idea_id": "uuid",
  "hypothesis": "경제/재무 논리 요약",
  "theme_tags": ["value", "quality", "momentum"],
  "target": {"instrumentType":"EQUITY","region":"USA","universe":"TOP3000","delay":1},
  "candidate_datasets": ["pv1","fundamental6"],
  "keywords_for_retrieval": ["earnings","surprise","mean reversion"]
}
```

### 8.2 CandidateAlpha (FastExpr Builder 출력 표준)

```json
{
  "idea_id": "uuid",
  "alpha_id": null,
  "simulation_settings": {
    "type": "REGULAR",
    "settings": {
      "instrumentType":"EQUITY",
      "region":"USA",
      "universe":"TOP3000",
      "delay": 1,
      "decay": 15,
      "neutralization": "SUBINDUSTRY",
      "truncation": 0.08,
      "maxTrade": "ON",
      "pasteurization": "ON",
      "testPeriod": "P1Y6M",
      "unitHandling": "VERIFY",
      "nanHandling": "OFF",
      "language": "FASTEXPR",
      "visualization": false
    },
    "regular": "rank(ts_delta(log(close), 5))"
  },
  "generation_notes": {
    "used_fields": ["close"],
    "used_operators": ["rank","ts_delta","log"]
  }
}
```

### 8.3 AlphaResult (시뮬 후 저장 표준)

```json
{
  "idea_id": "uuid",
  "alpha_id": "alpha_xxx",
  "settings_fingerprint": "sha256(...)",
  "expression_fingerprint": "sha256(...)",
  "summary_metrics": {
    "sharpe": 1.32,
    "fitness": 1.05,
    "turnover": 25.1,
    "drawdown": -0.12,
    "coverage": 0.92
  },
  "recordsets_saved": ["pnl","turnover","yearly-stats","daily-pnl"],
  "created_at": "..."
}
```

---


## 체크리스트
- [ ] IdeaSpec (LLM 출력 표준)
- [ ] CandidateAlpha (FastExpr Builder 출력 표준)
- [ ] AlphaResult (시뮬 후 저장 표준)
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
