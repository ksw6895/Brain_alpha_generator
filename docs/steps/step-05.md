# Step 5

## FastExpr 지식베이스 구축 (에이전트가 “정확히” 쓰게 만드는 핵심 장치)


### 5.1 왜 지식베이스가 필요한가?

* operators/data-fields 수가 많아 LLM 컨텍스트에 전부 넣을 수 없다.
* 따라서:

  1. 로컬 DB에 저장
  2. 키워드/임베딩 기반 검색으로 “관련 operator/field subset”만 추출
  3. 그 subset + 강제 규칙(정적검증)만 LLM에 제공
     → 이 구조가 실패율과 비용을 급격히 낮춘다.

### 5.2 Retrieval 설계(간단 버전)

* 입력: 아이디어 텍스트(예: “earnings surprise mean reversion, quality factor, volatility scaling”)
* 검색:

  * operators: definition/description에 대한 BM25/키워드 매칭
  * fields: description에 대한 키워드 매칭
* 출력:

  * operator 후보 Top-K(예: 50개)
  * field 후보 Top-K(예: 50개)
  * dataset 후보 Top-K(예: 20개)

### 5.3 Retrieval 설계(고급 버전)

* operators/fields description을 embedding
* FAISS 인덱스 구축
* 매 요청마다 Top-K를 추출

---


## 체크리스트
- [ ] 왜 지식베이스가 필요한가?
- [ ] Retrieval 설계(간단 버전)
- [ ] Retrieval 설계(고급 버전)
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
