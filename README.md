# AI 소비 패턴 분석 및 절약 코치
<img width="1917" height="947" alt="image" src="https://github.com/user-attachments/assets/96d199f6-15d0-4d5d-838b-fb528dc3e7ca" />

## 1. 프로젝트 소개 — 문제 정의와 해결 방식
**문제**: 지출을 줄이고 싶어도 기록·해석·실천 세 단계에서 막힙니다.
- **기록**: 가계부 수기 입력이 번거로워 오래 못 씀
- **해석**: 합계·그래프만으로는 무엇을 줄여야 할지 모름
- **실천**: 일반 AI 채팅은 내 데이터 근거 없이 그럴듯한 숫자를 지어냄

**해결**
| 단계 | 기능 | AI 기술 요소 |
|------|------|-------------|
| 기록 | 카드·은행 앱 캡처, 영수증 → AI가 날짜·금액·가맹점·카테고리 인식 → 확인 표에서 고친 뒤 저장 | **멀티모달 AI** |
| 해석 | 이번 달 지출·월말 예상·지난달 같은 기간 대비, **카테고리별 지난달 대비 증감률**, 카테고리 색으로 나눈 월별 막대(막대 위 전월 대비 %), 소비 알림 카드 | 코드 계산 |
| 실천 | AI 코치가 내 지출 데이터를 직접 조회해 근거와 함께 답하고, 월 목표 제안 → 사용자가 [적용] | **AI Agent** |

원칙은 **"계산은 코드, 읽기·해석·제안은 AI"** 입니다. 합계·비율·날짜·중복 판단은 코드가 하고, AI 답변에는 "AI 생성" 표시와 조회 근거를 함께 보여줍니다.

## 2. 팀원 및 역할
| 이름 | 역할 | 담당 업무 |
|------|------|-----------|
| 박채원 | Backend/DB | 프로젝트 관리, FastAPI API·Firestore 설계, 로그인·보안, 통합 및 배포 확인 |
| 안소연 | Frontend | 대시보드·업로드·채팅 화면 구현, UI/UX 설계, 실사용자 테스트 진행·피드백 정리 |
| 곽승렬 | AI Agent/Data | AI Agent 도구·프롬프트 설계, 소비 분석 로직, Agent 정량 평가, 필수 기능 3회 검증 |

### 실제 기여 내용 · 담당 코드 · GitHub 작업 기록

| 이름 | 담당 코드·문서 |
|------|---------------|
| 박채원 | `backend/main.py`<br>`backend/app/routers/`<br>`user_service.py` · `transaction_service.py`<br>`firestore.rules` · `render.yaml` |
| 안소연 | `frontend/index.html` · `app.js` · `style.css` · `auth.js`<br>`docs/UT_GUIDE.md` · `USER_FEEDBACK.md` |
| 곽승렬 | `services/agent_tools.py` · `chat_service.py` · `vision_service.py`<br>`upload_service.py` · `summary_service.py` · `goal_service.py` · `insight_service.py`<br>`backend/eval/`<br>`docs/G4_CHECKLIST.md` · `TEST_RESULTS.md` |

전체 진행 과정과 주요 의사결정은 [PROGRESS_LOG](docs/PROGRESS_LOG.md)에 날짜별로 기록했습니다.

## 3. 기술 스택과 선정 이유
| 영역 | 기술 | 선정 이유 |
|------|------|----------|
| AI | OpenAI gpt-4o-mini | 이미지 인식·구조화 출력·Function Calling을 한 모델로 처리, 저렴함(채팅 1회 약 2~4원) |
| Backend | Python 3.12, FastAPI, Pydantic / Render | 요청·Agent 도구 인자 검증을 Pydantic으로 통일, API 문서 자동 생성 |
| DB · 인증 | Firebase Firestore, Firebase Auth (Google, 익명) | 사용자별 데이터 분리, 비밀번호 미보관, 익명 로그인으로 체험 모드 제공 |
| Frontend | HTML, CSS, JavaScript / Vercel | 빌드 도구 없이 배포, 차트는 SVG로 직접 구현 |
| 운영 | UptimeRobot | 무료 서버 잠듦 방지 (10분 간격 `/health` 확인) |
| 테스트 | FastAPI TestClient, Playwright, Agent 평가 스크립트 | API 키 없이 규칙 검증, 화면 확인, Agent 정량 비교 |


## 4. 시스템 아키텍처
<img width="2640" height="1440" alt="system_architecture" src="https://github.com/user-attachments/assets/44a6b481-3d96-468f-b5f8-0e07e6a90087" />


## 5. 핵심 AI 활용 — 구현 근거

### 5-1. 멀티모달 AI — 캡처·영수증 인식
- 이미지 → gpt-4o-mini Vision이 정해진 JSON 형식(Structured Outputs)으로 거래 후보 추출
- 날짜 머리글별로 거래를 묶어 받고, 날짜 글자("18일(수)")는 **코드가 다시 해석** → 화면에 없는 연·월은 요일이 맞는 가장 가까운 과거 날짜로 정하고 "확인해 주세요" 표시
- 원본 이미지는 저장하지 않고, 확인 표에서 사용자가 고친 뒤 저장
- 코드: `backend/app/services/vision_service.py`, `upload_service.py`

### 5-2. AI Agent — 절약 코치
- Function Calling 반복 루프: 질문에 필요한 도구를 **7개 중 스스로 골라** 조회 (거래 검색, 월 요약, 두 달 비교, 카테고리 추이, 과소비 탐지, 목표 진행 상황, 목표 변경 제안 / 최대 5단계)
- 답변 전 스스로 점검(self-check), 조회 근거(trace)를 화면에 표시
- 목표는 **제안만** 하고 사용자가 [적용]해야 저장
- 코드: `backend/app/services/agent_tools.py`, `chat_service.py`

## 6. 대표 시연 시나리오
1. **캡처로 지출 기록** — 샘플 카드 내역 캡처 업로드 → 확인 표에 거래가 채워짐(월이 없는 날짜도 요일로 정확히 추정) → 저장 → 대시보드 금액 갱신
2. **근거 있는 소비 분석** — "지난달이랑 비교해서 어디서 많이 썼어?" → Agent가 비교·과소비 도구를 골라 조회 → 실제 금액과 근거 표시
3. **절약 목표 설정** — "이번 달 절약 목표 세워줘" → 이미 쓴 금액을 반영한 목표 제안 카드 → [적용] → 목표 진행률과 소비 알림 카드 갱신

## 7. AI 기능별 테스트 결과
| 기능 | 테스트 방법 | 결과 |
|------|------------|------|
| 멀티모달 AI | 샘플 이미지 3장(카드·통장·영수증) × 3회 | 개선 후 3회 모두 기대 결과와 일치 (개선 전 카드 목록 1건 3회 모두 오답) |
| AI Agent | 질문 15개 × 3회, 이전 방식(데이터 요약을 프롬프트에 넣는 방식)과 비교 | 도구 선택 15/15, 정답 일치 **5/10 → 10/10**, 지어낸 숫자 0건 |
| 전체 API | 자동 테스트 26개 섹션 (API 키 없이 가짜 모델) | 모두 통과 |
| 배포 환경 | 시크릿 창 접속, 체험 모드, 코치 질문 | 정상 동작, 답변 금액이 차트 금액과 일치 |

자세한 내용: [TEST_RESULTS](docs/TEST_RESULTS.md) · 필수 기능 16개 3회 검증 기록: [G4_CHECKLIST](docs/Test_Results/G4_Test_Results.md)

## 8. 실사용자 테스트 결과
> 진행 방법 [UT_GUIDE](docs/UT_GUIDE.md) · 응답과 반영 기록 [USER_FEEDBACK](docs/USER_FEEDBACK.md)

- 테스터: 5명
- 주요 피드백 및 반영 사항:

| 피드백 | 출처 | 결과 |
|--------|------|------|
| "글자가 작아 오래 보면 눈이 피로하다" | T1 | **반영** — 상단 [가] 버튼으로 글자 크기 3단계, 채팅 줄 간격 확대 ([전후 화면](docs/ut_T1_font_before_after.png)) |
| "지출 내역을 한눈에 보고 분석하기 어렵다" | T1 | **반영** — 카테고리별 합계 칩(눌러서 거르기), 가맹점 검색, 금액순 정렬 ([전후 화면](docs/ut_T1_list_before_after.png)) |
| "로그인 오류가 해결되면 좋겠다" | T2 | **반영** — 로그인·새로고침·재로그인 시나리오 점검  |
| "분석과 그래프가 한눈에 보기 좋다" / "대화 기록을 다시 볼 수 있어 좋다" | T2 / T1 | 장점으로 유지 |

## 9. 사전평가 결과와 개선사항
사전평가 개선 보고서의 지적 사항을 기준별로 반영했습니다.
| 지적 사항 | 개선 내용 |
|----------|----------|
| 월이 없는 캡처의 날짜 오인식 | 날짜 글자를 코드가 해석하고 요일로 월 결정, 날짜 머리글별 묶음 방식으로 변경 |
| 평가자가 이미지 기능을 시험할 자료 없음 | 가상 데이터 샘플 이미지 3장과 기대 결과 제공 ([sample_images](docs/sample_images/README.md)) |
| 프론트 설정 파일에 키 노출 | 저장소에서 제외, 키 교체·이전 키 삭제, 시크릿 검사 스크립트 0건, Firestore 직접 접근 차단 |
| AI 실패에도 사용 한도 차감 | 실패 시 차감분 되돌림 |
| 배포 서버 첫 접속 지연 | UptimeRobot으로 잠듦 방지 |
| 필수 기능 3회 검증 기록 없음 | 시나리오·기록표 작성 ([G4_CHECKLIST](docs/G4_CHECKLIST.md)) |
| 기획서·명세서 빈칸, docs 미제출 | 테스트·개선 단계, 기술 선정 근거, 구현 현황 표를 채워 `docs/`에 정리 |

테스트하며 스스로 찾아 고친 문제: 진행 중인 달을 지난달 전체와 비교하던 왜곡(→ 같은 기간 비교), 이미 쓴 금액보다 낮은 목표 제안, 확인 표 금액 잘림·쉼표 미표시.

## 10. 실행 방법
### 요구사항
- Python 3.12
- OpenAI API 키, Firebase 프로젝트 (Firestore·Authentication, 서비스 계정 키)

### 설치 및 실행
```bash
git clone https://github.com/vlfgl/Final-Project
cd Final-Project

# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1            # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                   # OPENAI_API_KEY, Firebase 서비스 계정 경로 채우기
uvicorn main:app --reload --port 8000  # http://127.0.0.1:8000/docs

# Frontend (새 터미널)
cd frontend
cp config.example.js config.js         # Firebase 웹 설정 채우기 (커밋하지 않음)
python -m http.server 5500             # http://127.0.0.1:5500
```

```bash
cd backend && python tests/test_api.py      # 자동 테스트 (API 키 불필요)
cd backend && python -m eval.agent_eval     # Agent 정량 평가 (실제 GPT, 1회 약 100원)
python backend/scripts/check_secrets.py     # 커밋 전 시크릿 검사 (0건이어야 함)
```

## 11. 링크
- **배포 URL**: https://final-project-frontend-seven-beta.vercel.app
  - 계정 없이 **"로그인 없이 체험하기"** → 동의 → 6개월 샘플 지출 605건으로 바로 사용 (첫 접속 시 서버 깨우는 데 최대 1분)
- **최종 발표 자료**: [docs/presentation.pdf](docs/presentation.pdf)
- **시연 영상**: (작성 예정)
- 서비스 기획서: [docs/서비스_기획서.md](docs/서비스_기획서.md)
- 기능 요구 명세서: [docs/기능_요구_명세서.md](docs/기능_요구_명세서.md)
