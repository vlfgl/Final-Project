"""OpenAI 클라이언트 공용 모듈 (채팅·Agent·이미지 인식이 함께 쓴다)."""
from typing import Optional

from openai import OpenAI

from app.config import settings


class ChatError(Exception):
    pass


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if not settings.OPENAI_API_KEY:
        raise ChatError("OPENAI_API_KEY가 설정되지 않았습니다.")
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30)
    return _client
