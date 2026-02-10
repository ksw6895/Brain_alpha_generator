# Steps Roadmap (Active)

## 문서 목적
이 디렉토리는 "앞으로 구현할 작업"만 담는다.
이 문서 하나만 읽어도 신규 코드 에이전트가 프로젝트 방향을 이해하고 착수할 수 있어야 한다.

## 프로젝트 한 줄 목표
WorldQuant BRAIN용 FastExpr 알파를 LLM 기반 멀티 에이전트로 생성하되,
비용 폭증과 문법 오류를 막기 위해 Top-K retrieval + validation-first 루프를 강제한다.

## 현재 상태 (착수 시점 기준)
- 메타데이터 동기화 파이프라인은 이미 구현됨.
- operators/datasets/data-fields는 로컬 DB와 JSON 인덱스에 저장됨.
- 정적 검증기, 시뮬레이터, 평가기는 구현됨.
- 미완성 영역: LLM 오케스트레이션, 비용 제어, 생성-수정 자동 루프의 운영 완성도.

## 절대 원칙
1. 전체 metadata를 LLM prompt에 직접 넣지 않는다.
2. 아이디어별 Top-K subset만 LLM에 전달한다.
3. 정적검증 통과본만 시뮬레이션으로 보낸다.
4. 플랫폼용 파이프라인 결과와 실거래용 해석을 혼합하지 않는다.
5. 비용 절감만을 최적화하지 않는다. 탐색(explore) 예산을 별도로 유지한다.
6. 동일 오류 반복 시 축소만 하지 않고 retrieval 확장 경로를 반드시 제공한다.

## 권장 읽기 순서 (신규 에이전트)
1. `docs/baseguideline.md`
2. `architecture/current-workflow-map.md`
3. `docs/steps/README.md` (현재 문서)
4. 수행할 step 문서 (`step-17`부터 순차)

## Active Steps
- `docs/steps/step-17.md`: LLM 컨텍스트 게이팅 + Top-K retrieval 강제
- `docs/steps/step-18.md`: FastExpr 지식팩 구축(API + 실전 예시)
- `docs/steps/step-19.md`: 2-Agent 계약 설계(Idea Researcher / Alpha Maker)
- `docs/steps/step-20.md`: 토큰/비용 제어 레이어 및 retrieval budget 정책
- `docs/steps/step-21.md`: Validation-first 생성/수정 루프 + 시뮬/평가 연결

## 단계 의존성
- step-17 완료 후 step-18 착수
- step-18 완료 후 step-19 착수
- step-19 완료 후 step-20 착수
- step-20 완료 후 step-21 착수

## 작업 결과물 기준
각 step은 최소 아래를 남긴다.
1. 코드 변경 (필요 파일 명시)
2. 실행/검증 커맨드와 결과 요약
3. 실패 케이스와 재현 방법
4. 다음 step 진입 조건

## Retired
- 기존 완료 문서(`step-00~16`, `step-00~16-execution`)는 정리 후 제거됨.
- 제거 이력/사유: `docs/steps/retired-v1-steps.md`
