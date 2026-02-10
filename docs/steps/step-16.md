# Step 16

## (선택) wqb / WQ-Brain / ACE 라이브러리 활용 가이드


### 16.1 wqb 활용 포인트

* Permanent Session(만료 방지 세션), 비동기/동시 시뮬 지원
* operators/datasets/fields/alphas search & filter 기능이 정리되어 있음
* 단, submit는 “완성도/정책 변화” 이슈가 있을 수 있어 옵션으로 두고 직접 검증

### 16.2 ACE 라이브러리(플랫폼 제공 zip) 활용 포인트

* /operators, /data-sets, /data-fields 호출 래퍼가 있을 확률이 높음
* 있다면:

  * “메타데이터 동기화” 파트를 ACE로 대체
  * 에이전트 시스템은 ACE 위에서 orchestrate만 담당하도록 단순화 가능

---

# 끝.

## 체크리스트
- [ ] wqb 활용 포인트
- [ ] ACE 라이브러리(플랫폼 제공 zip) 활용 포인트
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
