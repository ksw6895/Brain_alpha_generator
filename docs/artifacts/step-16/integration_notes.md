# Integration Notes: wqb / ACE

## wqb
- Permanent Session, async simulation, search/filter 기능을 사용할 수 있음.
- 본 프로젝트에서는 API 래퍼를 기본으로 두고, 필요 시 `brain_api` 레이어를 wqb 어댑터로 교체 가능.

## ACE API [Gold]
- `ACE API [Gold]/ace_lib.py`의 세션/시뮬/메타 수집 로직을 참고해 현재 모듈화 구조로 분해 구현함.
- 직접 의존하지 않고 `src/brain_agent`로 정리해 유지보수성을 확보함.
- `ACE API [Gold]/how_to_use.ipynb`는 출력 제거로 경량화했으며, 구조 참고용 샘플은 `docs/artifacts/fixtures/`로 분리함.
