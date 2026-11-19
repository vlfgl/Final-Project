from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, require_consent
from app.config import settings
from app.schemas import BulkCreate, BulkResult, ExtractRequest, ExtractResponse
from app.services import upload_service, user_service
from app.services.llm import ChatError

router = APIRouter(prefix="/api", tags=["uploads"])


@router.post("/uploads/extract", response_model=ExtractResponse,
             summary="이미지 1장(카드 내역 캡처·영수증) → 거래 후보 추출 (저장하지 않음)")
def extract(payload: ExtractRequest, user: CurrentUser = Depends(require_consent)):
    try:
        remaining = user_service.consume_image_quota(user)
    except user_service.DailyLimitExceeded:
        raise HTTPException(429, f"오늘 이미지 인식 한도({settings.DAILY_IMAGE_LIMIT}장)를 모두 사용했어요. 내일 다시 이용해 주세요.")
    try:
        result = upload_service.extract_from_image(user, payload.data_url)
    except ChatError as e:
        raise HTTPException(502, str(e))
    return {**result, "remaining_today": remaining}


@router.post("/transactions/bulk", response_model=BulkResult, status_code=201,
             summary="확인한 거래 여러 건 한 번에 저장")
def bulk(payload: BulkCreate, user: CurrentUser = Depends(require_consent)):
    return {"created": upload_service.bulk_create(user.uid, payload.items)}
