from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, require_consent
from app.config import settings
from app.db import NotFoundError
from app.schemas import ChatRequest, ChatResponse
from app.services import chat_service, user_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse,
             summary="AI 채팅 (데이터 요약 → 시스템 프롬프트 주입 → GPT → 대화 자동 저장)")
def chat(payload: ChatRequest, user: CurrentUser = Depends(require_consent)):
    try:
        remaining = user_service.consume_chat_quota(user)
    except user_service.DailyLimitExceeded:
        raise HTTPException(429, f"오늘 채팅 한도({settings.DAILY_CHAT_LIMIT}회)를 모두 사용했어요. 내일 다시 이용해 주세요.")
    try:
        result = chat_service.chat(user.uid, payload.message, payload.conversation_id)
    except NotFoundError:
        raise HTTPException(404, "해당 대화를 찾을 수 없습니다.")
    except chat_service.ChatError as e:
        raise HTTPException(502, str(e))
    return {**result, "remaining_today": remaining}
