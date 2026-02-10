# Step 4

## FastExpr 메타데이터 수집 (핵심)


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



## Step 4 실행 결과
- 산출물 문서: `docs/step-04-execution.md`
- 구현 산출물/완료 범위/의존성은 실행 문서에 정리.

## 체크리스트
- [x] Operators (연산자) 메타데이터: GET /operators
- [x] Datasets 메타데이터: GET /data-sets
- [x] Data Fields(변수) 메타데이터: GET /data-fields
- [x] 로컬 저장 스키마(권장: SQLite)
- [x] “메타데이터 동기화 정책”
- [x] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
