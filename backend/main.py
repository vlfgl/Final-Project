import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, conversations, data, me

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finance-assistant")

app = FastAPI(
    title="AI 소비 패턴 분석 및 절약 코치 API",
    description="로그인한 사용자별 소비 데이터를 분석하고 AI가 절약 계획을 제안하는 백엔드. "
                "인증: Authorization: Bearer <Firebase ID 토큰>",
    version="1.0.0",
)

@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    """예상 못 한 예외를 500 JSON으로 바꾼다.
    CORS 미들웨어보다 안쪽에서 처리해야 500 응답에도 CORS 헤더가 붙는다.
    (그렇지 않으면 브라우저는 실제 에러 대신 '연결 실패'로만 보여준다.)
    내부 정보(키, 스택)는 응답에 노출하지 않고 서버 로그로만 남긴다."""
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다. 서버 로그를 확인하세요."})


# 나중에 추가한 미들웨어가 바깥쪽 → CORS가 가장 바깥에서 모든 응답(500 포함)에 헤더를 붙인다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(me.router)
app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/", tags=["health"])
def root():
    return {"service": "spending-coach", "docs": "/docs"}


@app.get("/health", tags=["health"], summary="헬스 체크 (콜드스타트 깨우기용)")
def health():
    return {"status": "ok"}
