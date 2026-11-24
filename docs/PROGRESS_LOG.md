# 프로젝트 진행 과정 기록 (PROGRESS_LOG)

AI 소비 패턴 분석 및 절약 코치의 개발 과정과 주요 의사결정을 GitHub 커밋 이력을 근거로 정리한다.

- 기간: 2026-11-01 ~ 2026-11-24 · 커밋 34개 · PR 1건
- 계정: 박채원 `chaewon`·`vlfgl` / 안소연 `soyeon74` / 곽승렬 `Kwak-gif`
- 전체 이력: [커밋 목록](https://github.com/vlfgl/Final-Project/commits/main)

## 1. 단계별 진행

| 날짜 | 단계 | 한 일 | 담당 | 대표 커밋 |
| --- | --- | --- | --- | --- |
| 11-01 | 저장소 생성 | 이전 과제(개인 재무 관리 AI 비서)의 FastAPI·Firestore·로그인 구조를 가져와 시작. 대화 기록, 소비 요약, 가상 지출 데이터 생성 | 박채원 | [`85e7223`](https://github.com/vlfgl/Final-Project/commit/85e7223) |
| 11-03 | 핵심 기능 뼈대 | 캡처·영수증 인식(`vision_service`), 확인 표를 거친 저장(`upload_service`), 거래 관리, 월 절약 목표 API와 화면 | 박채원, 곽승렬 | [`49a3086`](https://github.com/vlfgl/Final-Project/commit/49a3086), [`e12f370`](https://github.com/vlfgl/Final-Project/commit/e12f370) |
| 11-20 | **AI Agent 전환** | Function Calling 도구 7개(`agent_tools.py`), 조회 근거 표시, 목표 제안 카드, Agent 정량 평가 스크립트(`backend/eval/`) | 박채원, 곽승렬 | [`681ab44`](https://github.com/vlfgl/Final-Project/commit/681ab44) |
| 11-20 | 소비 알림 카드 | 코드 규칙으로 과소비·목표 초과를 계산하는 `/api/insights`와 카드 화면 | 박채원 | [`68653c0`](https://github.com/vlfgl/Final-Project/commit/68653c0) |
| 11-20 | 보안·평가 대비 | `config.js` 저장소 제외와 키 교체, Firestore 규칙, 시크릿 검사 스크립트, 평가용 샘플 이미지 3장, AI 실패 시 사용 한도 환불 | 박채원, 안소연 | [`df11f69`](https://github.com/vlfgl/Final-Project/commit/df11f69) |
| 11-20~21 | 프론트엔드 개선 | 금액 입력 쉼표 자동 표시, HEIC 사진 사전 안내, 썸네일 메모리 해제 | 안소연 | [`445afd8`](https://github.com/vlfgl/Final-Project/commit/445afd8), [`67115da`](https://github.com/vlfgl/Final-Project/commit/67115da) |
| 11-21~22 | **이미지 인식 날짜 개선** | 날짜 머리글별 묶음 방식으로 응답 형식 변경, 월이 없는 날짜를 요일로 결정. 브랜치 `KSR/BACKEND`에서 작업 후 PR로 병합 | 곽승렬 | [`50d8434`](https://github.com/vlfgl/Final-Project/commit/50d8434), [PR #1](https://github.com/vlfgl/Final-Project/pull/1) |
| 11-22 | 필수 기능 검증 | Must 기능 16개를 배포 환경에서 3회씩 실행, 화면 증거 6장 | 곽승렬 | [`2a30082`](https://github.com/vlfgl/Final-Project/commit/2a30082) |
| 11-22 | 문서 제출 | 서비스 기획서, 기능 요구 명세서 | 박채원 | [`cd05a2a`](https://github.com/vlfgl/Final-Project/commit/cd05a2a) |
| 11-23 | 팀 내부 사전 테스트 | 팀 내부에서 핵심 흐름 사전 점검 | 안소연 | [`6120ee0`](https://github.com/vlfgl/Final-Project/commit/6120ee0) |
| 11-23 | README·발표 자료 | README를 제출 항목 10개 형식으로 재구성, 시스템 아키텍처 그림 교체, 발표 자료 PDF | 박채원 | [`f20ed2e`](https://github.com/vlfgl/Final-Project/commit/f20ed2e), [`86b1fc3`](https://github.com/vlfgl/Final-Project/commit/86b1fc3), [`6238ec3`](https://github.com/vlfgl/Final-Project/commit/6238ec3) |
| 11-24 | 실사용자 피드백 | 외부 사용자 2명 피드백 기록(이름·프로필 가림) | 안소연 | [`2b67af9`](https://github.com/vlfgl/Final-Project/commit/2b67af9) |
| 11-24 | 역할 정리 | 기획서·README 팀원 역할 표 갱신 | 박채원 | [`6664662`](https://github.com/vlfgl/Final-Project/commit/6664662) |

## 2. 주요 의사결정

| 시기 | 결정 | 검토한 대안 | 근거 |
| --- | --- | --- | --- |
| 11-01~03 | 입력은 카드·은행 앱 캡처와 영수증 이미지 | 카드사 엑셀, 수기 입력 | 사용자는 지출을 휴대폰 앱에서 본다. 엑셀은 카드사마다 양식이 달라 후순위로 내렸다. |
| 11-01~03 | 계산은 코드, 읽기·해석·제안은 AI | AI가 합계·날짜까지 판단 | 이전 과제에서 GPT가 데이터에 없는 금액을 지어냈다. |
| 11-01~03 | 인식 결과는 확인 표를 거쳐 저장 | 인식 즉시 저장 | 출금 부호 오판, 한글 가맹점명 오인식이 실제로 발생했다. |
| 11-20 | AI 코치를 요약 주입 방식에서 AI Agent로 전환 | 월 요약을 프롬프트에 넣는 방식 유지 | "카페 몇 번 갔어?" 같은 개별 거래 질문에 답하지 못했다. 질문 15개 평가에서 정답 일치 5/10 → 10/10. |
| 11-20 | 진행 중인 달은 지난달 **같은 기간**과 비교 | 지난달 전체와 비교 | 20일치를 한 달 전체와 비교하면 모든 카테고리가 '감소'로 나오는 왜곡이 있었다. |
| 11-20 | 목표는 Agent가 제안만, 저장은 사용자가 [적용] | Agent가 바로 저장 | AI 실수로 데이터가 바뀌지 않게 한다. 이미 쓴 금액보다 낮은 한도는 도구가 거부한다. |
| 11-20 | 장기 메모리·RAG 제외 | 대화에서 성향 추출·저장, 문서 검색 | 답의 근거는 사용자 본인의 거래 데이터라 도구로 직접 조회하는 편이 정확하다. 두 기술 요소(멀티모달·Agent)의 완성도를 우선했다. |
| 11-20 | 소비 알림 카드는 코드 규칙으로 계산 | 접속할 때마다 AI 분석 | 질문하지 않아도 비용이 나가고, 무료 서버에서 화면이 늦게 뜬다. |
| 11-20 | Firebase 웹 설정을 저장소에서 빼고 키 교체 | 웹 apiKey는 공개 값이므로 유지 | 평가 기준상 키 노출은 폐기·재발급 대상이다. Firestore 규칙으로 브라우저의 DB 직접 접근도 막았다. |
| 11-21 | 날짜는 화면 글자를 받아 코드가 해석, 목록은 날짜 머리글별로 묶음 | AI가 연·월·일을 채움, 행마다 날짜를 붙임 | AI가 화면에 없는 월을 추측했고, 머리글 아래 두 번째 행에 다른 날짜를 붙이는 오류가 3회 중 3회 발생했다. 수정 후 3회 중 3회 정확. |

## 3. 검증 기록

- 필수 기능 16개 × 3회: [G4_Test Results.md](Test%20Results/G4_Test%20Results.md)
- 팀 내부 사전 테스트: [AI_Coach_Internal_Test_2026-11-23.md](Test%20Results/AI_Coach_Internal_Test_2026-11-23.md)
- Agent 정량 평가: `backend/eval/results/` (2026-11-20, 6회 실행 기록)
- 자동 테스트: `python backend/tests/test_api.py` (섹션 1~25)
- 실사용자 피드백: [USER_FEEDBACK.md](USER_FEEDBACK.md)

