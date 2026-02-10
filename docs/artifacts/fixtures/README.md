# API Response Fixtures (Sample)

이 디렉토리는 Brain API fetch 결과의 형태를 빠르게 확인/테스트하기 위한 샘플 JSON 모음입니다.
실제 운영 시에는 최신 API 응답을 다시 fetch해서 사용하세요.

## Files
- `simulations_options.sample.json`: `OPTIONS /simulations` 샘플
- `operators.sample.json`: `GET /operators` 샘플
- `datasets.sample.json`: `GET /data-sets` 샘플
- `data_fields.sample.json`: `GET /data-fields` 샘플
- `alpha.sample.json`: `GET /alphas/{alpha_id}` 샘플
- `recordsets/pnl.sample.json`: `GET /alphas/{alpha_id}/recordsets/pnl` 샘플
- `diversity.sample.json`: `GET /users/self/activities/diversity` 샘플

## Note
- fixture는 "스키마/필드 구조 참고"가 목적입니다.
- 값 자체를 신뢰해 의사결정하지 마세요.
