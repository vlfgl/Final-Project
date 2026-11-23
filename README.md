# AI 소비 패턴 분석 및 절약 코치

## 프로젝트 소개
카드·은행 앱 캡처나 영수증을 올리면 AI가 날짜·금액·가맹점·카테고리를 읽어 지출을 정리하고,
이번 달 지출·월말 예상·지난달 같은 기간 대비와 카테고리별 차트, 과소비 알림 카드로 소비 패턴을 보여주는 서비스입니다.
AI 코치(AI Agent)는 질문에 맞는 지출 데이터를 직접 조회해 근거와 함께 절약 방법을 답하고, 월 목표를 제안하면 사용자가 [적용]으로 반영합니다.


## 팀원 및 역할
| 이름 | 역할 | 담당 업무 |
|------|------|-----------|
| 박채원 | Backend/DB | 프로젝트 관리, FastAPI API·Firestore 설계, 로그인·보안, 통합 및 배포 확인 |
| 안소연 | Frontend | 대시보드·업로드·채팅 화면 구현, UI/UX 설계, 실사용자 테스트 진행·피드백 정리 |
| 곽승렬 | AI Agent/Data | AI Agent 도구·프롬프트 설계, 소비 분석 로직, Agent 정량 평가, 필수 기능 3회 검증 |

## 기술 스택
- **AI**: OpenAI gpt-4o-mini (Vision + Structured Outputs, Function Calling)
- **Backend**: Python 3.12, FastAPI, Pydantic, Render
- **Frontend**: HTML, CSS, JavaScript (ES 모듈, SVG 차트 직접 구현), Vercel
- **DB · 인증**: Firebase Firestore, Firebase Authentication (Google, 익명 체험 모드)
- **운영**: UptimeRobot (무료 서버 잠듦 방지, 10분 간격 `/health` 확인)
- **테스트**: FastAPI TestClient + 메모리 DB, Playwright, Agent 정량 평가 스크립트

## 시스템 아키텍처
![시스템 아키텍처](docs/images/system_architecture.png)

## 핵심 AI 활용

### 1. 멀티모달 AI — 캡처·영수증 인식
- 이미지 1장 → gpt-4o-mini Vision이 정해진 JSON 형식(Structured Outputs)으로 거래 후보 추출
- 화면의 날짜 머리글별로 거래를 묶어 받고, 날짜 글자("18일(수)")는 코드가 다시 해석
  → 화면에 없는 연도·월은 요일이 맞는 가장 가까운 과거 날짜로 정하고 "확인해 주세요" 메모 표시
- 사용자가 확인 표에서 고친 뒤 저장 (원본 이미지는 저장하지 않음), 이미지 간 중복 자동 표시
- 결과: 샘플 이미지 3장 3회 반복 모두 기대 결과와 일치 (개선 전 카드 목록 1건 3회 모두 오답)

### 2. AI Agent — 절약 코치
- Function Calling 반복 루프: 질문에 필요한 도구를 **7개 중 직접 골라** 조회하고 결과로 답변
  (거래 검색, 월 요약, 두 달 비교, 카테고리 추이, 과소비 탐지, 목표 진행 상황, 목표 변경 제안 / 최대 5단계, 단계당 최대 4회 호출)
- 답변 전 스스로 점검(self-check), 조회 근거(trace)를 화면에 함께 표시
- 목표는 **제안만** 하고 사용자가 [적용]을 눌러야 저장, 이미 쓴 금액보다 낮은 한도는 제안하지 않음
- 결과(질문 15개, 3회 반복): 도구 선택 15/15, 정답 일치 **이전 방식 5/10 → Agent 10/10**, 지어낸 숫자 0건

## 실행 방법
### 요구사항
- Python 3.12
- OpenAI API 키, Firebase 프로젝트(Firestore·Authentication, 서비스 계정 키)
- 프론트엔드는 빌드 도구가 없어 Node.js 불필요

### 설치 및 실행
```bash
git clone <https://github.com/vlfgl/Final-Project>
cd <저장소 폴더>

# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # OPENAI_API_KEY, Firebase 서비스 계정 경로 채우기
uvicorn main:app --reload --port 8000  # http://127.0.0.1:8000/docs

# Frontend (새 터미널)
cd frontend
cp config.example.js config.js       # Firebase 웹 설정 채우기 (config.js는 커밋하지 않음)
python -m http.server 5500           # http://127.0.0.1:5500
```

```bash
# 자동 테스트 (API 키 불필요, 마지막 줄 ALL TESTS PASSED)
cd backend && python tests/test_api.py
# AI Agent 정량 평가 (실제 GPT 사용, 1회 약 100원)
cd backend && python -m eval.agent_eval
# 커밋 전 시크릿 검사 (저장소 루트에서, 0건이어야 함)
python backend/scripts/check_secrets.py
```

## 사용자 테스트 결과
> 진행 예정 — 진행 방법은 [UT_GUIDE](docs/UT_GUIDE.md), 결과 기록은 [USER_FEEDBACK](docs/USER_FEEDBACK.md)
- 테스터: (5명, 구성)
- 주요 피드백 및 반영 사항:
  - "(피드백)" → (반영 내용)

## 링크
- 배포 URL: https://final-project-frontend-seven-beta.vercel.app
  - 별도 계정 없이 **"로그인 없이 체험하기"** → 동의 → 6개월 샘플 지출 605건으로 바로 사용
  - 이미지 인식은 [샘플 이미지 3장](docs/sample_images/README.md)으로 테스트 (첫 접속 시 서버 깨우는 데 최대 1분)
- 서비스 기획서: [docs/서비스_기획서.md](docs/서비스_기획서.md)
- 기능 요구 명세서: [docs/기능_요구_명세서.md](docs/기능_요구_명세서.md)
- 테스트 결과: [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) · [docs/G4_CHECKLIST.md](docs/G4_CHECKLIST.md)
- 진행 기록: [docs/PROGRESS_LOG.md](docs/PROGRESS_LOG.md)
- 발표 자료: /docs/presentation.pdf (작성 예정)
- 시연 영상: (작성 예정)
