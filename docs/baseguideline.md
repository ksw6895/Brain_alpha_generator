# WorldQuant BRAIN API + 알파 리서치 에이전트 시스템 통합 가이드 (WSL/Windows)

> 목표:
> 1) BRAIN API로 FastExpr 실험(시뮬레이션/결과 수집)을 자동화
> 2) FastExpr 메타데이터(operators / datasets / data-fields)를 API로 동기화해 “표현식 생성 에이전트”가 정확히 동작
> 3) 멀티 에이전트 파이프라인(아이디어 수집 → FastExpr 변환 → 시뮬 → 평가/피드백 → (옵션) 제출)을 만들어
>    “고품질 알파를 지속 생산”하는 시스템을 설계/구현

---

## 0. 운영 원칙 / 리스크 관리 (반드시 읽고 설계에 반영)

### 0.1 ToS/정책 준수
- 기본: **공식 Brain API를 우선 사용**한다.
- 크롤링/복사는 최후의 수단:
  - (1) API로 메타데이터/문서가 부족한 경우에만,
  - (2) 플랫폼 약관/robots/접근 정책을 위반하지 않는 범위에서,
  - (3) 요청 간격/부하를 최소화하고, 인증 우회/보안 우회는 절대 하지 않는다.

### 0.2 “백테스트 성과 ↔ 실거래 가능성” 분리
- 지금 단계는 “컨설턴트 fee/포인트 확보를 위한 플랫폼 제출”이 목적.
- 실거래 목적은 별도 백테스터/데이터/슬리피지/거래비용/리밸런싱 구현이 필요하므로,
  **플랫폼용 알파 생산 파이프라인**과 **실거래용 리서치 파이프라인**을 분리 설계한다.

### 0.3 자동화의 핵심 병목 3개
1) 메타데이터 동기화(operators/data-fields/datasets) 품질
2) FastExpr 정적 검증(타입/스코프/문법) → “시뮬 실패율”을 줄이는 것이 생산성의 핵심
3) 평가/피드백 루프(검색/돌연변이/파라미터 탐색) → “학습 가능한 자동화”로 만든다

---

## 1. WSL(Windows) 개발 환경 세팅

### 1.1 추천 스택
- Python 3.11+ (wqb도 3.11+ 권장)
- 패키지(권장):
  - requests (기본 API)
  - pydantic (스키마/검증)
  - pandas (레코드셋 처리)
  - tenacity (재시도/backoff)
  - rich 또는 loguru (로그)
  - sqlite3/duckdb (로컬 저장)
  - (선택) aiohttp/httpx (비동기)
  - (선택) faiss / rank-bm25 (메타데이터 검색)

### 1.2 WSL에서 프로젝트 폴더 생성
```bash
# WSL Ubuntu 예시
mkdir -p ~/wqbrain-agent
cd ~/wqbrain-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel setuptools
````

### 1.3 requirements.txt 예시

```txt
requests>=2.31
pydantic>=2.6
pandas>=2.1
tenacity>=8.2
python-dotenv>=1.0
rich>=13.7
```

---

## 2. Brain API “최초 사용” 단계 (인증/세션)

> 문서 1의 핵심: `/authentication`에 Basic Auth로 POST → 세션 쿠키(JWT)가 세팅됨.
> 이후 Session을 유지하면서 `/simulations`, `/alphas`, `/recordsets`를 호출.

### 2.1 크리덴셜 저장 (최소 방식: ~/.brain_credentials)

* WSL 홈: `/home/<user>/`
* 파일: `~/.brain_credentials`
* 내용(JSON): `["<email>", "<password>"]`
* 권한:

```bash
chmod 600 ~/.brain_credentials
```

### 2.2 BrainAPISession(권장 구현: “자동 재로그인” 포함)

#### 2.2.1 설계 요구사항

* `requests.Session()` 기반
* `POST /authentication`로 로그인
* `GET /authentication`로 로그인 상태/토큰 만료를 점검하고 필요 시 재로그인
* Biometrics(인증 앱/브라우저 확인) 흐름도 처리(문서 1 참고)

#### 2.2.2 코드 스켈레톤

```python
# src/brain_api/client.py
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import requests
from urllib.parse import urljoin

API_BASE = "https://api.worldquantbrain.com"

@dataclass
class BrainCredentials:
    email: str
    password: str

def load_credentials(path: str | Path) -> BrainCredentials:
    p = Path(path).expanduser()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return BrainCredentials(email=raw[0], password=raw[1])

class BrainAPISession:
    def __init__(self, creds: BrainCredentials, expiry_buffer_sec: int = 60):
        self.creds = creds
        self.expiry_buffer_sec = expiry_buffer_sec
        self.s = requests.Session()
        self.s.auth = (creds.email, creds.password)

    def auth_post(self) -> requests.Response:
        return self.s.post(f"{API_BASE}/authentication")

    def auth_get(self) -> requests.Response:
        return self.s.get(f"{API_BASE}/authentication")

    def ensure_login(self) -> None:
        """
        - 이미 로그인 상태면 OK
        - 만료 임박이면 재로그인
        - 204면 미로그인 → 로그인
        - 401 persona면 biometrics URL 안내 후 재시도
        """
        r = self.auth_get()
        if r.status_code == 200:
            payload = r.json()
            expiry = payload.get("token", {}).get("expiry", 0)
            if isinstance(expiry, (int, float)) and expiry > self.expiry_buffer_sec:
                return
            # 만료 임박 → 재로그인
            self._login_flow()
            return
        if r.status_code == 204:
            self._login_flow()
            return
        if r.status_code == 401:
            # 미인증/만료/정책 등
            self._login_flow()
            return
        # 기타: raise
        r.raise_for_status()

    def _login_flow(self) -> None:
        r = self.auth_post()
        if r.status_code == 201:
            return
        if r.status_code == 401:
            # biometrics sign-in enabled 인 경우 persona 헤더/Location 제공 가능
            if r.headers.get("WWW-Authenticate") == "persona" and "Location" in r.headers:
                url = urljoin(r.url, r.headers["Location"])
                print(f"[ACTION REQUIRED] Open this URL in a browser and complete biometrics:\n{url}")
                input("After completing biometrics, press Enter to continue...")
                # biometrics 완료 후 다시 POST
                r2 = self.s.post(url)
                r2.raise_for_status()
                return
            # reCAPTCHA required 등 (문서 1 참고) - 구현 옵션:
            raise RuntimeError(f"Unauthorized: {r.text}")
        r.raise_for_status()
```

---

## 3. “유효한 시뮬 설정” 자동 추출 (OPTIONS /simulations)

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

## 4. FastExpr 메타데이터 수집 (핵심)

> 여기서부터 “표현식 생성 에이전트”의 정확도가 결정된다.
> 가능한 한 API로 수급하고, 부족하면 웹 문서(Operators 페이지 등)로 보강한다.

### 4.1 Operators (연산자) 메타데이터: GET /operators

* 수집 항목(최소):

  * name, category, (가능하면) scope, definition, description, level, documentation
* 저장:

  * `data/meta/operators_<date>.json`
  * * 파생: `operators.parquet` 또는 sqlite table

### 4.2 Datasets 메타데이터: GET /data-sets

* 파라미터(예시): instrumentType, region, delay, universe, theme, search, category, limit/offset
* 저장:

  * `data/meta/datasets_<region>_<delay>_<universe>_<date>.json`

### 4.3 Data Fields(변수) 메타데이터: GET /data-fields

* 핵심 파라미터:

  * dataset.id=<dataset_id>
  * instrumentType, region, delay, universe
  * type=<MATRIX|VECTOR|GROUP|UNIVERSE|...>
  * search, limit, offset
* 페이지네이션 필수 (limit/offset)

### 4.4 로컬 저장 스키마(권장: SQLite)

* operators

  * name TEXT PK
  * category TEXT
  * scope TEXT NULL
  * definition TEXT NULL
  * description TEXT NULL
  * level TEXT NULL
  * documentation TEXT NULL
  * fetched_at DATETIME
* datasets

  * id TEXT PK
  * name TEXT
  * description TEXT
  * region TEXT
  * delay INT
  * universe TEXT
  * coverage REAL NULL
  * valueScore REAL NULL
  * fieldCount INT NULL
  * alphaCount INT NULL
  * userCount INT NULL
  * themes JSON NULL
  * fetched_at DATETIME
* data_fields

  * id TEXT PK
  * dataset_id TEXT
  * region TEXT
  * delay INT
  * universe TEXT
  * type TEXT (MATRIX/VECTOR/GROUP/UNIVERSE)
  * description TEXT
  * coverage REAL NULL
  * alphaCount INT NULL
  * userCount INT NULL
  * themes JSON NULL
  * fetched_at DATETIME

### 4.5 “메타데이터 동기화 정책”

* 최소:

  * 매일 1회(또는 실행 시 1회) `/operators` 동기화
  * region/delay/universe 조합별 `/data-sets`, `/data-fields` 동기화
* 고급:

  * “필요할 때만” 동기화:

    * (1) cache miss
    * (2) 검색 결과가 너무 빈약할 때
    * (3) 시뮬 실패율이 증가할 때(=메타 오래됨 신호)

---

## 5. FastExpr 지식베이스 구축 (에이전트가 “정확히” 쓰게 만드는 핵심 장치)

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

## 6. FastExpr “정적 검증” 최소 규칙 (시뮬 실패율을 줄이는 장치)

> 완전한 타입 시스템을 처음부터 구현하기 어렵다면,
> **(1) 토큰 검증 + (2) 괄호/인자 개수 + (3) 필드/연산자 존재성 + (4) 스코프 규칙**만으로도
> 시뮬 실패율을 크게 줄일 수 있다.

### 6.1 토큰/문법 최소 검증

* 허용 토큰:

  * operator name (from /operators)
  * data field id (from /data-fields)
  * 숫자 상수(정수/소수)
  * 괄호 (), 콤마, 공백
* 괄호 밸런스 체크
* “함수 호출” 패턴: `name(arg1, arg2, ...)`

### 6.2 스코프(scope) 규칙

* operator.scope가 제공되는 경우:

  * REGULAR: regular 식에서만 사용
  * SELECTION/COMBO: SuperAlpha에서만 사용
* scope 정보가 없으면:

  * 우선은 REGULAR만 사용하도록 whitelist(안전 모드) 운영

### 6.3 필드 타입(type) 규칙(점진적 강화)

* data field type이 MATRIX/VECTOR/GROUP/UNIVERSE로 제공될 수 있다.
* 초기 안전 규칙(예):

  * Time-series 계열(ts_*)은 MATRIX 입력만 허용
  * Group 계열(group_*)은 GROUP + MATRIX 조합만 허용
  * VECTOR 필드는 “벡터 연산자(예: vec_*)”로 먼저 변환하거나, VECTOR을 허용하는 operator에만 연결
* 이 규칙은 운영하면서 “실패 로그 기반”으로 점진적으로 확장한다.

### 6.4 정적 검증 실패 시 행동

* 즉시 재생성(rewrite) 요청:

  * “사용 불가 operator/field” 목록을 LLM에 돌려주고 수정하도록 한다.
* “연속 3회 실패”하면:

  * 해당 아이디어를 폐기 or 더 안전한 템플릿으로 다운그레이드

---

## 7. 멀티 에이전트 시스템 설계 (핵심)

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

## 8. 데이터 스키마 (파이프라인 안정화를 위한 최소 저장 구조)

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

## 9. 시뮬레이션 자동화 (문서 1 기반)

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

## 10. 평가/필터링/랭킹 (Evaluator Agent)

### 10.1 기본 통과 필터(초기값, 정책으로 분리)

* 최소 요구:

  * sharpe >= 1.25
  * fitness >= 1.0
  * turnover in (1, 70)  # 너무 낮으면 신호 없음, 너무 높으면 과매매
  * weight concentration이 과도하지 않을 것(플랫폼에 지표가 있으면 활용)
* 주의: 이 기준은 “초기 정책”이다. 계정/대회/시기마다 실제 제출 기준은 다를 수 있으므로 설정파일로 분리한다.

### 10.2 안정성 점검(추천)

* yearly-stats가 있으면:

  * 연도별 Sharpe, PnL, drawdown의 일관성(“한 해만 튄 알파” 제거)
* daily-pnl이 있으면:

  * PnL 분포의 fat-tail/급락 구간 확인
  * 상관 기반 중복 제거에 사용(아래)

### 10.3 상관/중복 제거 (제출 전 필수)

* recordset의 daily-pnl 또는 pnl 시계열을 이용해:

  * 기존 “제출 후보 집합”과의 상관행렬 계산
  * |corr| > 0.7 이상은 같은 클러스터로 묶고 대표 1개만 남김
* 클러스터 대표 선정 기준:

  * Sharpe 우선, 다음 fitness, 다음 turnover 안정성

---

## 11. 피드백/돌연변이/탐색 (Feedback Agent)

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

## 12. (옵션) 제출 자동화 (Submit Agent)

> 공식 문서 1에 제출 API가 명시되어 있지 않은 경우가 많다.
> 따라서 “옵션 모듈”로 설계하고, 실제 동작은 계정 권한/서버 응답으로 확인한다.

### 12.1 추정되는 제출 흐름(예시)

1. POST `/alphas/{alpha_id}/submit`

   * 403이면 서버 체크 실패(또는 권한 부족)
   * 그 외 201이면 제출 프로세스 시작/확인
2. GET `/alphas/{alpha_id}/submit` 를 재시도(필요시 Retry-After 준수)
3. 결과 JSON 저장

### 12.2 제출 전 체크리스트(필수)

* 통과 필터 충족
* 상관/중복 제거 통과
* 다양성 정책(Region/Delay/DataCategory) 목표와 충돌하지 않음
* 오늘 제출량/레이트리밋 체크

---

## 13. 다양성/전략 포트폴리오 관리

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

## 14. 구현 체크리스트 (코드 에이전트용 “Done Definition”)

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

## 15. 추천 운영 전략(“고품질 알파”를 계속 생산하는 방법론)

1. 초기 2주:

* “안전 템플릿 + 제한된 operator subset”만 사용해 시뮬 실패율을 5% 이하로 낮춘다.
* 목적: 파이프라인 안정화/데이터 축적

2. 다음 2~4주:

* 실패 로그 기반으로 타입 규칙/템플릿 확장
* dataset 다양화(coverage 높은 것부터)

3. 이후:

* 상관/클러스터링 기반으로 제출 후보를 “포트폴리오”로 관리
* 다양한 region/delay로 확장해 “제출 다양성”을 점수화

---

## 16. (선택) wqb / WQ-Brain / ACE 라이브러리 활용 가이드

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

````
