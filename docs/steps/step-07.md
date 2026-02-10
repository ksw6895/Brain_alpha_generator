# Step 7

## 멀티 에이전트 시스템 설계 (핵심)


### 7.1 전체 아키텍처(추천: 파이프라인 + 이벤트 로그)

```
[Metadata Sync] → [Idea Collector] → [Field/Operator Retrieval] → [FastExpr Builder]
     ↓                                                        ↓
  (DB/cache)                                             [Static Validator]
                                                            ↓
                                                     [Simulation Runner]
                                                            ↓
                                                     [Result Collector]
                                                            ↓
                                                     [Evaluator/Ranker]
                                                            ↓
                                                     [Feedback/Mutator]
                                                            ↓
                                                 (Loop) or (Submit Queue)
```

### 7.2 에이전트 역할 정의 (RACI)

1. **MetaSync Agent**

* 책임: /operators, /data-sets, /data-fields, OPTIONS /simulations 동기화
* 산출물: local DB + index

2. **Idea Collector Agent**

* 책임: “경제/재무 논리” 기반 아이디어 후보 생성
* 입력: 타겟 시장(USA/TOP3000 등), 사용 가능한 dataset 카테고리, 최근 성과 통계
* 출력: IdeaSpec(JSON)

3. **FastExpr Builder Agent**

* 책임: IdeaSpec → FastExpr expression 생성
* 입력: IdeaSpec + (retrieval subset: operators/fields) + 강제 규칙
* 출력: CandidateAlpha(JSON: expression + settings)

4. **Simulation Runner Agent**

* 책임: /simulations 제출, Retry-After 준수 폴링, alpha_id 수집
* 출력: AlphaResultRaw(JSON), recordsets

5. **Evaluator Agent**

* 책임: 성과지표 계산/필터링/랭킹 + 실패 원인 분류
* 출력: ScoreCard + FailureReason

6. **Feedback/Mutator Agent**

* 책임: ScoreCard/FailureReason 기반 수정안 생성
* 방법:

  * 파라미터 탐색(decay/truncation/neutralization)
  * 표현식 변형(연산자 교체, 윈도우 변경, 정규화 추가)
* 출력: New CandidateAlpha들(다음 루프 투입)

7. **(옵션) Submit Agent**

* 책임: 제출 기준 충족 + 중복/상관/다양성 체크 후 제출 요청
* 출력: 제출 결과(성공/거절 사유)

---


## 체크리스트
- [ ] 전체 아키텍처(추천: 파이프라인 + 이벤트 로그)
- [ ] 에이전트 역할 정의 (RACI)
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
