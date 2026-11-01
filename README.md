# AI 소비 패턴 분석 및 절약 코치

카드 내역이나 영수증을 올리면 AI가 소비 패턴을 분석하고, 매달 절약 목표를 함께 관리해 주는 개인 절약 코치.

> 진행 중. 현재 구현: **로그인(Google · 체험 모드) · 개인정보 동의 · 사용자별 데이터 분리 · 내 데이터 삭제 · 하루 채팅 제한**
> + 이전 과제(개인 재무 관리 AI 비서)의 데이터 CRUD · 요약 · AI 채팅 · 대화 기록.

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic |
| DB / 인증 | Firebase Firestore, Firebase Authentication (Google, 익명) |
| AI | OpenAI API (gpt-4o-mini) |
| Frontend | HTML / CSS / JavaScript (ES 모듈), Firebase JS SDK (CDN) |
| 배포 | Render (백엔드), Vercel (프론트엔드) |

## 인증 구조

```
브라우저 ──(Google 로그인 / 익명 체험)──▶ Firebase Auth
   │  ID 토큰 (1시간, SDK가 자동 갱신)
   ▼
FastAPI ── Authorization: Bearer <ID 토큰> 검증 (firebase_admin) ──▶ uid
   └─ users/{uid}/transactions, users/{uid}/conversations 만 접근
```

- `require_user`: 로그인 확인 (`/api/me`, 동의, 삭제)
- `require_consent`: 로그인 + 동의 확인 (데이터 · AI 기능 전부). 동의 전이면 `403 consent_required` → 프론트가 동의 화면 표시
- 체험 모드(익명 로그인)는 동의 후 샘플 지출 데이터 667건이 자동으로 채워지고, 로그아웃하면 삭제됨
- `DELETE /api/me`: 사용자의 모든 데이터 + 프로필 + Firebase 계정 삭제

Swagger(`/docs`)에서 테스트할 때는 우측 상단 **Authorize**에 ID 토큰을 넣는다.
(브라우저 콘솔에서 로그인 상태로 `await (await import('./auth.js')).getIdToken()` 실행)

## Firebase 설정 (새 프로젝트)

1. Firestore Database 만들기
2. Authentication → 로그인 방법 → **Google**, **익명** 사용 설정
3. Authentication → 설정 → **승인된 도메인**에 `localhost`(기본 포함)와 배포한 Vercel 도메인 추가
4. 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성 → 백엔드용 JSON
5. 프로젝트 설정 → 일반 → 내 앱 → 웹 앱(`</>`) 추가 → `firebaseConfig` 값 → 프론트용

## 로컬 실행

```bash
# 백엔드
cd backend
py -3.12 -m venv venv && .\venv\Scripts\Activate.ps1   # macOS/Linux: python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                   # 키 채우기
uvicorn main:app --reload                              # http://127.0.0.1:8000/docs

# 프론트엔드 (frontend/config.js의 FIREBASE_CONFIG를 먼저 채울 것)
cd frontend
python -m http.server 5500                             # http://localhost:5500
```

테스트: `python tests/test_api.py` (메모리 DB + 가짜 토큰 `dev:<uid>`로 인증·사용자 분리·동의·삭제·한도 검증)

## 환경 변수

**Backend (Render)**

| 이름 | 설명 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | 서비스 계정 JSON 전체 (로컬은 `FIREBASE_SERVICE_ACCOUNT_PATH`) |
| `ALLOWED_ORIGINS` | CORS 허용 도메인, 쉼표 구분 |
| `DAILY_CHAT_LIMIT` | 사용자별 하루 채팅 횟수, 기본 50 |
| `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `CHAT_HISTORY_LIMIT` | 선택 |

**Frontend (Vercel)**

| 이름 | 설명 |
|---|---|
| `API_BASE_URL` | 백엔드 주소 |
| `FIREBASE_CONFIG` | `firebaseConfig`를 JSON 한 줄로: `{"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}` |
