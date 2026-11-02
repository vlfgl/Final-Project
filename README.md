# AI 소비 패턴 분석 및 절약 코치

카드 내역이나 영수증을 올리면 AI가 소비 패턴을 분석하고, 매달 절약 목표를 함께 관리해 주는 개인 절약 코치.

> 진행 중. 현재 구현: **로그인(Google · 체험 모드) · 개인정보 동의 · 사용자별 데이터 분리 · 내 데이터 삭제 · 하루 채팅 제한 · 거래 CRUD · **이미지 인식(카드 내역 캡처·영수증)** · 소비 요약 · AI 채팅 · 대화 기록**

## 필수 기술 요소 충족 현황

| 요소 | 상태 | 근거 및 현황 |
| :--- | :---: | :--- |
| **멀티모달 AI** | ✅ 완료 | 카드·통장 캡처와 영수증 이미지를 Vision 모델로 입력받아 거래 내역을 추출하고 자동으로 분류함 |
| **AI Agent** | ❌ 아직 | 현재 코치는 요약을 프롬프트에 넣고 GPT를 단발성으로 호출하는 구조임. 과제 정의인 "의도 파악 및 도구 활용(Function Calling)을 통한 목표 달성" 구조 구현 필요 |
| **Long-term Memory** | ⚠️ 일부 | **구현됨:** 사용자별 대화 저장·불러오기, 대화 내 맥락 유지, 사용자 수정 분류 기억 및 재적용<br>**미흡:** 대화 속 성향·선호 추출 및 차후 활용(예: "커피는 못 줄여요" 등 기억). 과제 기준인 "선호도 저장·활용"에는 추가 보완 필요 |

## 데이터 모델

`users/{uid}/transactions/{id}` — 결제 1건

| 필드 | 설명 | 예시 |
|---|---|---|
| `date` | 결제일 | `"2026-10-28"` |
| `amount` | 금액(원, 양의 정수) | `5600` |
| `merchant` | 가맹점 | `"스타벅스 강남역점"` |
| `category` | 고정 목록 중 하나: 식비 · 배달 · 카페·간식 · 장보기·생활 · 교통 · 쇼핑 · 주거·통신 · 구독 · 문화·여가 · 의료·건강 · 교육 · 기타 | `"카페·간식"` |
| `source` | 입력 경로: `manual` · `screenshot` · `receipt` · `sample` | `"screenshot"` |
| `category_by` | 분류 주체: `ai` · `user` (사용자가 고친 분류는 이후 자동 분류에 반영 예정) | `"ai"` |
| `memo`, `created_at` | 메모(선택), 저장 시각 | |

## API

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/me` | 내 정보 + 동의 여부 |
| POST | `/api/me/consent` | 개인정보·AI 처리 동의 |
| DELETE | `/api/me` | 내 데이터 전체 + 계정 삭제 |
| POST | `/api/me/demo` | 체험 계정에 샘플 데이터(6개월, 605건) 채우기 |
| POST | `/api/uploads/extract` | 이미지 1장 → 거래 후보 추출 (저장 안 함, 하루 한도) |
| POST | `/api/transactions/bulk` | 확인한 거래 일괄 저장 (최대 300건) |
| GET | `/api/transactions/categories` | 카테고리 목록 |
| GET | `/api/transactions/summary` | 소비 요약 (이번 달은 오늘 기준, 월초 7일간은 월평균 비교 생략, 월별 카테고리 합계 포함) |
| GET/POST | `/api/transactions` | 거래 목록(`start`, `end`, `limit`, `order`) / 직접 추가 |
| PUT/DELETE | `/api/transactions/{id}` | 거래 수정(부분) / 삭제 |
| GET | `/api/goals/{YYYY-MM}` | 월 목표 + 진행률·페이스 (없으면 이전 달 목표 이어받음) |
| PUT/DELETE | `/api/goals/{YYYY-MM}` | 월 목표 저장(변경 이력 기록) / 해제 — 지난 달은 불가 |
| GET | `/api/goals/{YYYY-MM}/suggestion` | 추천 목표 (최근 3개월 평균, AI 미사용) |
| GET/POST | `/api/conversations` | 대화 목록 / 저장 |
| GET/DELETE | `/api/conversations/{id}` | 대화 불러오기 / 삭제 |
| POST | `/api/chat` | AI 코치 채팅 (하루 한도 적용) |

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic |
| DB / 인증 | Firebase Firestore, Firebase Authentication (Google, 익명) |
| AI | OpenAI API (gpt-4o-mini) |
| Frontend | HTML / CSS / JavaScript (ES 모듈), Firebase JS SDK (CDN) |
| 배포 | Render (백엔드), Vercel (프론트엔드) |

## 이미지 인식 흐름 (멀티모달 AI)

```
[이미지 여러 장 선택] → 브라우저에서 축소(JPEG) → 1장씩 POST /api/uploads/extract
   → Vision 모델: 이미지 종류 판별 + 거래 목록 + 카테고리 (Structured Outputs로 JSON 형식 강제)
   → 코드 후처리: 연도 보정 · 취소 제외 · 기존 거래와 중복 표시 · 사용자가 고친 가맹점 분류 규칙 적용
[확인 표] 날짜·가맹점·금액·카테고리 수정, 체크 → POST /api/transactions/bulk
```

- **AI는 읽기만, 판단은 코드가**: 연도 추정 오류·중복·취소 처리를 규칙으로 처리해 결과가 일관되고 테스트 가능함
- **원본 이미지는 저장하지 않음**: 추출된 거래 정보만 저장 (동의서 내용과 일치)
- **사람 확인 단계**: 흐릿하게 읽힌 값·날짜 없는 행·중복·취소는 표시되고 기본 체크 해제
- 겹치게 찍은 캡처 간 중복은 프론트에서 한 번 더 표시

## 월 절약 목표

- `users/{uid}/goals/{YYYY-MM}`: 총예산 + 카테고리 한도(최대 3개) + 변경 이력
- 목표가 없는 달은 가장 최근 목표를 **이어서 적용**(저장은 사용자가 할 때만), 지난 달은 수정 불가(기록 보존)
- 진행률·월말 예상·남은 날 하루 사용 가능 금액은 코드로 계산. 상태: 목표 안쪽 / 초과 예상 / 초과
- 추천: 최근 3개월 평균에서 총예산 −10%, 고정비(주거·통신·구독·교육·의료)를 뺀 상위 3개 카테고리 −15%
- AI 코치 시스템 프롬프트에 이번 달 목표와 진행 상황을 함께 넣어 목표 기준으로 조언

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
