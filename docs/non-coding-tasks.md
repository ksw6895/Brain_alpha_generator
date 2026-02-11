# 코딩 외 작업 관리 문서

## 사용 규칙
- 이 문서는 개발 코드 변경 없이도 진행 가능한 업무를 기록한다.
- 모든 작업자는 새 항목을 추가할 때 `ID`, `상태`, `담당`, `증빙`을 채운다.
- 상태값은 `TODO`, `DOING`, `DONE`, `BLOCKED` 중 하나만 사용한다.
- 항목 완료 시 날짜를 `YYYY-MM-DD` 형식으로 기록한다.

## 작업 목록
| ID | 작업 | 상태 | 담당 | 증빙/링크 | 완료일 |
|---|---|---|---|---|---|
| NC-001 | WorldQuant Brain ToS/정책 최신본 확인 및 팀 공유 | TODO | 미정 | 정책 문서 링크 추가 |  |
| NC-002 | 플랫폼용 파이프라인 vs 실거래용 파이프라인 경계 검토 회의 진행 | TODO | 미정 | 회의록 링크 추가 |  |
| NC-003 | 제출 정책(Sharpe/Fitness/Turnover 기준) 운영 합의안 작성 | TODO | 미정 | 운영 합의 문서 링크 추가 |  |
| NC-004 | Diversity 목표(region/delay/dataCategory) 월간 목표치 확정 | TODO | 미정 | 목표표 링크 추가 |  |
| NC-005 | Step 진행 리뷰 루틴(주간 점검 시간/담당자) 확정 | TODO | 미정 | 캘린더/노션 링크 추가 |  |
| NC-006 | Step 1 WSL 개발 환경 세팅 산출물 정리 및 의존성 기록 | DONE | Codex | docs/steps/retired-v1-steps.md (기존 증빙 문서 정리됨) | 2026-02-10 |
| NC-007 | Step 2~16 실행 산출물 문서화 및 의존성 기록 | DONE | Codex | docs/steps/retired-v1-steps.md (기존 증빙 문서 정리됨) | 2026-02-10 |
| NC-008 | 완료된 step 문서(00~16) 정리/삭제 및 향후 step(17~21) 로드맵 문서 신설 | DONE | Codex | docs/steps/README.md, docs/steps/step-17.md ~ docs/steps/step-21.md | 2026-02-10 |
| NC-009 | step-17~21 문서를 신규 코드 에이전트 온보딩 가능 수준으로 보강(흐름/의도/입출력/검증 기준 명시) | DONE | Codex | docs/steps/README.md, docs/steps/step-17.md ~ docs/steps/step-21.md | 2026-02-10 |
| NC-010 | 토큰 절감으로 인한 탐색력 훼손 리스크 보강(이중 예산, 확장 분기, 포맷 복구, 품질 KPI) 반영 | DONE | Codex | docs/steps/README.md, docs/steps/step-17.md, docs/steps/step-18.md, docs/steps/step-19.md, docs/steps/step-20.md, docs/steps/step-21.md | 2026-02-10 |
| NC-011 | step-17~21에 프론트엔드/관측성 병렬 트랙(F-Track) 통합(Neural Cosmos, Brain Terminal, Arena, Evolutionary Tree 계약 반영) | DONE | Codex | docs/steps/README.md, docs/steps/step-17.md, docs/steps/step-18.md, docs/steps/step-19.md, docs/steps/step-20.md, docs/steps/step-21.md | 2026-02-10 |
| NC-012 | architecture/current-workflow-map.md 정합성 최신화(현재 코드 이벤트/저장 경로 + step-17~21/F-Track 병렬 흐름 반영) | DONE | Codex | architecture/current-workflow-map.md | 2026-02-10 |
| NC-013 | step-19 구현 완료 후 문서 동기화(DoD 체크/로드맵 상태/구현 보고서 반영) | DONE | Codex | docs/steps/README.md, docs/steps/step-19.md, docs/artifacts/step-19/implementation_report.md, architecture/current-workflow-map.md | 2026-02-11 |
| NC-014 | OpenAI SDK/Structured Output 반영에 따른 step-19 문서/가이드 업데이트 | DONE | Codex | README.md, docs/steps/step-19.md, docs/artifacts/step-19/implementation_report.md, architecture/current-workflow-map.md, .env.example | 2026-02-11 |
| NC-015 | step-20 최종 문서 동기화(reactor_status/HUD/API/실측 백테스트 반영) 및 step-21 실측 제약 보정 | DONE | Codex | docs/steps/step-20.md, docs/steps/step-21.md, docs/steps/README.md, docs/artifacts/step-20/implementation_report.md, data/probes/step20/* | 2026-02-12 |
| NC-016 | step-20 실측 재실행(rerun) 저장 성공본 반영 및 step-21 payload 매핑 보정(`is/train/test/checks`) | DONE | Codex | data/probes/step20/alpha_result_probe_rerun.json, data/probes/step20/simulation_events_probe_rerun.json, docs/steps/step-20.md, docs/steps/step-21.md, docs/artifacts/step-20/implementation_report.md | 2026-02-12 |

## 업데이트 로그
- 2026-02-10: 초안 생성 (Step 0 완료 후 최초 등록)
- 2026-02-10: NC-006 완료 (Step 1 산출물/의존성 문서화)
- 2026-02-10: NC-007 완료 (Step 2~16 산출물/체크리스트 문서화)
- 2026-02-10: NC-008 완료 (완료된 step 문서 정리/삭제 + 신규 로드맵 step 작성)
- 2026-02-10: NC-009 완료 (신규 에이전트 착수 가능하도록 step-17~21 문서 구조 보강)
- 2026-02-10: NC-010 완료 (탐색력 훼손 리스크 완화 정책을 step-17~21에 반영)
- 2026-02-10: NC-011 완료 (step-17~21에 프론트엔드 병렬 트랙 계약/이벤트/시각화 요구사항 반영)
- 2026-02-10: NC-012 완료 (architecture 문서를 현재 코드/계획 정합성 기준으로 업데이트)
- 2026-02-11: NC-013 완료 (step-19 구현 결과를 step 문서/로드맵/아키텍처 문서/구현 리포트에 동기화)
- 2026-02-11: NC-014 완료 (OpenAI SDK/Structured Output 반영으로 step-19 문서/환경가이드 업데이트)
- 2026-02-12: NC-015 완료 (step-20 최종 구현/실측 결과 반영 + step-21 실측 제약 보정)
- 2026-02-12: NC-016 완료 (실측 rerun 저장 성공본으로 step-20/21 문서 보정)
