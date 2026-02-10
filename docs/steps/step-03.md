# Step 3

## “유효한 시뮬 설정” 자동 추출 (OPTIONS /simulations)


> 목적:
>
> * Region/Universe/Neutralization 등 가능한 값을 하드코딩하지 않고 OPTIONS로 동기화
> * 표현식 생성/시뮬 요청 전 “사전 검증”에 사용

### 3.1 구현 요구사항

* `OPTIONS /simulations` 호출
* 응답 JSON에서:

  * instrumentType, region, universe, neutralization, language 등 allowed values를 추출
* 로컬 저장: `data/meta/simulations_options.json` (날짜 버전 태그 포함)

### 3.2 활용

* 파이프라인은 config로 “타겟 조합”을 하나 지정(초기 추천):

  * instrumentType=EQUITY, region=USA, universe=TOP3000, delay=1, language=FASTEXPR
* 이후 “다양성 확보” 단계에서 region/delay를 확장

---


## 체크리스트
- [ ] 구현 요구사항
- [ ] 활용
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
