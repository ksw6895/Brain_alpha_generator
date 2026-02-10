# Step 9

## 시뮬레이션 자동화 (문서 1 기반)


### 9.1 기본 시뮬 요청

* POST `/simulations` with JSON body(CandidateAlpha.simulation_settings)
* 응답 헤더 `Location`에 progress URL
* progress URL을 GET 폴링:

  * `Retry-After` 헤더가 있으면 그 초만큼 대기
  * 없으면 완료
* 완료되면 response body의 `alpha` 필드에서 alpha_id 획득
* GET `/alphas/{alpha_id}`로 상세 조회

### 9.2 멀티 시뮬(2~10개)

* POST `/simulations`에 배열로 여러 개 제출
* parent simulation의 children 목록을 획득 후 각각 결과 수집
* 목표: 파라미터 탐색(윈도우/decay 등) 효율 극대화

### 9.3 “중복 시뮬 방지”

* 로컬 DB에 아래 fingerprint 저장:

  * fingerprint = sha256( settings_canonical_json + "::" + expression_string )
* fingerprint가 이미 있으면 제출 스킵
* (추가) “거의 동일” 표현식은 AST normalize 후 hash (옵션)

---



## Step 9 실행 결과
- 산출물 문서: `docs/step-09-execution.md`
- 구현 산출물/완료 범위/의존성은 실행 문서에 정리.

## 체크리스트
- [x] 기본 시뮬 요청
- [x] 멀티 시뮬(2~10개)
- [x] “중복 시뮬 방지”
- [x] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
