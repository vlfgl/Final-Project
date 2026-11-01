from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, require_consent, require_user
from app.services import user_service

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", summary="내 정보 + 동의 여부 (로그인 직후 호출)")
def me(user: CurrentUser = Depends(require_user)):
    return user_service.get_profile(user)


@router.post("/consent", summary="개인정보 수집·AI 처리 동의")
def consent(user: CurrentUser = Depends(require_user)):
    return user_service.give_consent(user)


@router.delete("", summary="내 데이터 전체 삭제 + 계정 삭제")
def delete_me(user: CurrentUser = Depends(require_user)):
    return user_service.delete_all_data(user)


@router.post("/demo", summary="체험 계정(익명)에 샘플 데이터 채우기")
def demo(user: CurrentUser = Depends(require_consent)):
    if not user.is_anonymous:
        raise HTTPException(400, "체험 데이터는 '로그인 없이 체험하기'에서만 사용할 수 있습니다.")
    return user_service.seed_demo_data(user)
