# Step 13

## 다양성/전략 포트폴리오 관리


### 13.1 Diversity endpoint 활용(문서 1에 있음)

* GET `/users/<userid>/activities/diversity?grouping=region,delay,dataCategory`
* 목적:

  * “내가 어떤 region/delay/dataCategory에 편중되어 있는지” 파악
  * IdeaCollector가 다음 아이디어를 “빈 약한 영역”으로 유도하는 정책 피드백에 사용

### 13.2 운영 정책 예시

* 한 달 목표:

  * region 2~3개, delay 2개, dataCategory 다변화
* 제출 큐는 “다양성 점수”를 가중치로 포함:

  * `final_score = alpha_score + lambda * diversity_bonus`

---


## 체크리스트
- [ ] Diversity endpoint 활용(문서 1에 있음)
- [ ] 운영 정책 예시
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
