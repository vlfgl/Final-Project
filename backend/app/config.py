"""환경 변수 로딩. 키/시크릿은 절대 코드에 하드코딩하지 않는다."""
import os
from dotenv import load_dotenv

load_dotenv()


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # 비용 제한: 답변 최대 토큰, 프롬프트에 포함할 이전 메시지 수
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "500"))
    CHAT_HISTORY_LIMIT: int = int(os.getenv("CHAT_HISTORY_LIMIT", "10"))
    # agent: 모델이 도구를 골라 호출하는 방식(기본) | baseline: 요약을 프롬프트에 넣는 이전 방식(비교용)
    COACH_MODE: str = os.getenv("COACH_MODE", "agent").lower()
    # 한 질문에서 모델이 도구를 부를 수 있는 최대 단계 수 (무한 반복·비용 폭주 방지)
    AGENT_MAX_STEPS: int = int(os.getenv("AGENT_MAX_STEPS", "5"))
    AGENT_MAX_CALLS_PER_STEP: int = int(os.getenv("AGENT_MAX_CALLS_PER_STEP", "4"))

    # 이미지 인식(Vision) 모델과 응답 토큰 상한 — 한 장에 거래가 많으면 출력이 길어져서 채팅보다 크게
    OPENAI_VISION_MODEL: str = os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    VISION_MAX_TOKENS: int = int(os.getenv("VISION_MAX_TOKENS", "2500"))
    # 사용자별 하루 이미지 인식 장수 상한 (비용 안전장치)
    DAILY_IMAGE_LIMIT: int = int(os.getenv("DAILY_IMAGE_LIMIT", "30"))

    # 사용자별 하루 채팅 횟수 상한 (비용 안전장치)
    DAILY_CHAT_LIMIT: int = int(os.getenv("DAILY_CHAT_LIMIT", "50"))
    # 동의서 내용이 바뀌면 버전을 올려 재동의를 받는다
    CONSENT_VERSION: str = os.getenv("CONSENT_VERSION", "2026-11-01")

    # 둘 중 하나: JSON 문자열(Render 권장) 또는 파일 경로(로컬)
    FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")

    # firestore(기본) | memory(로컬 테스트용, 재시작 시 초기화)
    DB_BACKEND: str = os.getenv("DB_BACKEND", "firestore").lower()

    ALLOWED_ORIGINS: list[str] = _list(
        os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000")
    )


settings = Settings()
