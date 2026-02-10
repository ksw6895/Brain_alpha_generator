# Step 11

## 피드백/돌연변이/탐색 (Feedback Agent)


### 11.1 실패 원인 분류 템플릿

* Sharpe 낮음:

  * 노이즈 과다 → smoothing(ts_mean), winsorization, rank/zscore 추가
* Turnover 과다:

  * decay 증가, signal smoothing, ts_delay 도입, truncation 강화
* Coverage 낮음:

  * 결측 많음 → 다른 dataset/field로 대체, nanHandling 정책 수정
* 특정 섹터/산업 편향:

  * neutralization 강화(SUBINDUSTRY→INDUSTRY 등), group operator로 균형 조정

### 11.2 파라미터 탐색(자동)

* 윈도우 d 후보:

  * [3,5,10,20,40,60,120] 처럼 제한된 set
* decay 후보:

  * [5,10,15,20,30]
* truncation 후보:

  * [0.05,0.08,0.1,0.13]
* 위 조합을 multi-simulation(2~10) 단위로 잘라 제출

### 11.3 표현식 변형(자동)

* operator swap:

  * ts_mean ↔ ts_median
  * rank ↔ zscore
  * ts_delta ↔ (x - ts_delay(x, d))
* structure mutation:

  * `rank(ts_delta(log(x), d))` → `rank(ts_mean(ts_delta(log(x), d), k))`
  * `zscore(x)` 추가/삭제
* 단, 정적검증 통과한 변형만 시뮬 제출

---



## Step 11 실행 결과
- 산출물 문서: `docs/step-11-execution.md`
- 구현 산출물/완료 범위/의존성은 실행 문서에 정리.

## 체크리스트
- [x] 실패 원인 분류 템플릿
- [x] 파라미터 탐색(자동)
- [x] 표현식 변형(자동)
- [x] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
