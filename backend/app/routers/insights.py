from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_consent
from app.services import insight_service

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("", summary="소비 알림 카드 (AI 미사용: 과소비 규칙·목표 진행률로 계산, 하루 한도 차감 없음)")
def get_insights(user: CurrentUser = Depends(require_consent)):
    return insight_service.build(user.uid)
