"""Pydantic 스키마: 요청 검증과 응답 형태를 한 곳에서 정의한다."""
from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_AMOUNT = 100_000_000  # 1억 원: 오타로 인한 비정상 입력 방지


# ---------- 거래 ----------
# 카테고리는 고정 목록: AI가 임의의 이름을 만들지 못하게 하고, 통계를 정확하게 하기 위함
CATEGORIES = (
    "식비", "배달", "카페·간식", "장보기·생활", "교통", "쇼핑",
    "주거·통신", "구독", "문화·여가", "의료·건강", "교육", "기타",
)
Category = Literal[CATEGORIES]  # type: ignore[valid-type]
Source = Literal["manual", "screenshot", "receipt", "sample"]


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class TransactionCreate(BaseModel):
    date: Date = Field(..., description="결제일 (YYYY-MM-DD)", examples=["2026-10-28"])
    amount: int = Field(..., gt=0, le=MAX_AMOUNT, description="결제 금액(원)", examples=[5600])
    merchant: str = Field(..., min_length=1, max_length=100, description="가맹점", examples=["스타벅스 강남역점"])
    category: Category = Field(..., description="소비 카테고리 (고정 목록)", examples=["카페·간식"])
    memo: str = Field("", max_length=200, description="메모(선택)")

    _s = field_validator("merchant", "memo", mode="before")(_strip)

    @field_validator("merchant")
    @classmethod
    def merchant_not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("가맹점을 입력해 주세요.")
        return v


class TransactionUpdate(BaseModel):
    """부분 수정: 보낸 필드만 변경된다."""
    date: Optional[Date] = None
    amount: Optional[int] = Field(None, gt=0, le=MAX_AMOUNT)
    merchant: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[Category] = None
    memo: Optional[str] = Field(None, max_length=200)

    _s = field_validator("merchant", "memo", mode="before")(_strip)


class BulkItem(TransactionCreate):
    """이미지 인식 → 사용자가 확인한 거래. 출처와 분류 주체를 함께 저장한다."""
    source: Literal["screenshot", "receipt"]
    category_by: Literal["ai", "user", "rule"] = "ai"


class BulkCreate(BaseModel):
    items: list[BulkItem] = Field(..., min_length=1, max_length=300)


class BulkResult(BaseModel):
    created: int


class ExtractRequest(BaseModel):
    # 프론트에서 축소한 이미지를 data URL로 보낸다 (원본 파일은 서버에 저장하지 않음)
    data_url: str = Field(..., max_length=8_000_000, pattern=r"^data:image/(png|jpeg|jpg|webp);base64,",
                          description="data:image/jpeg;base64,... (최대 약 6MB)")


class ExtractedItem(BaseModel):
    date: Optional[str] = Field(None, description="YYYY-MM-DD, 못 읽었으면 null")
    amount: int
    merchant: str
    category: str
    category_by: Literal["ai", "rule"]
    status: Literal["spent", "income", "canceled"]
    low_confidence: bool
    duplicate: bool
    include: bool = Field(..., description="확인 표에서 기본 체크 여부")
    notes: list[str] = Field(default_factory=list, description="사용자에게 보여줄 확인 사항")


class ExtractResponse(BaseModel):
    image_type: Literal["card_statement", "transaction_detail", "receipt", "other"]
    items: list[ExtractedItem]
    remaining_today: int


# ---------- 월 절약 목표 ----------
class CategoryLimit(BaseModel):
    category: Category
    limit: int = Field(..., gt=0, le=MAX_AMOUNT)


class GoalSave(BaseModel):
    total_budget: int = Field(..., gt=0, le=MAX_AMOUNT, description="월 총예산(원)", examples=[1500000])
    category_limits: list[CategoryLimit] = Field(default_factory=list, max_length=3,
                                                 description="카테고리 한도 (최대 3개)")


class TransactionOut(BaseModel):
    id: str
    date: str
    amount: int
    merchant: str
    category: str
    source: str = "manual"
    category_by: str = "user"
    memo: str = ""
    created_at: str = ""


class Metrics(BaseModel):
    total: int
    average: int = Field(..., description="건당 평균 지출")
    daily_average: int = Field(..., description="일평균 지출(기간 전체 일수 기준)")
    monthly_average: int
    max: dict
    min: dict


class Summary(BaseModel):
    period: str
    count: int
    metrics: Metrics
    trend: str
    current_month: dict
    monthly_totals: dict[str, int]
    categories: list[dict] = Field(..., description="카테고리별 합계, 금액 큰 순")
    monthly_categories: dict[str, list[dict]] = Field(default_factory=dict, description="월별 카테고리 합계")


# ---------- 대화 ----------
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    messages: list[Message] = Field(..., min_length=1)


class ConversationListItem(BaseModel):
    """목록 응답에는 messages를 포함하지 않는다(가볍게). 전체는 GET /api/conversations/{id}."""
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationDetail(ConversationListItem):
    messages: list[Message]


# ---------- 채팅 ----------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, examples=["이번 달 지출 어때?"])
    conversation_id: Optional[str] = Field(None, description="이어서 대화할 경우 기존 대화 ID")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("메시지가 비어 있습니다.")
        return v.strip()


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    summary: Summary
    remaining_today: int = Field(..., description="오늘 남은 채팅 횟수")
