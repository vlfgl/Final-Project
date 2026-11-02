from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import CurrentUser, require_consent
from app.db import NotFoundError
from app.schemas import CATEGORIES, Summary, TransactionCreate, TransactionOut, TransactionUpdate
from app.services import summary_service, transaction_service

# 모든 거래 API는 로그인 + 동의한 사용자만, 그리고 본인 데이터만 다룬다.
router = APIRouter(prefix="/api/transactions", tags=["transactions"])

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


# 고정 경로는 경로 변수 라우트보다 먼저 선언한다.
@router.get("/categories", response_model=list[str], summary="사용 가능한 카테고리 목록")
def categories():
    return list(CATEGORIES)


@router.get("/summary", response_model=Summary, summary="소비 요약 (대시보드 + AI 프롬프트용)")
def get_summary(user: CurrentUser = Depends(require_consent)):
    return summary_service.get_summary(user.uid)


@router.get("", response_model=list[TransactionOut], summary="거래 목록 조회")
def list_transactions(
    start: Optional[str] = Query(None, pattern=DATE_PATTERN, description="시작일 YYYY-MM-DD"),
    end: Optional[str] = Query(None, pattern=DATE_PATTERN, description="종료일 YYYY-MM-DD"),
    limit: Optional[int] = Query(None, ge=1, le=2000),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    user: CurrentUser = Depends(require_consent),
):
    return transaction_service.list_transactions(user.uid, start, end, limit, descending=(order == "desc"))


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED, summary="거래 직접 추가")
def create_transaction(payload: TransactionCreate, user: CurrentUser = Depends(require_consent)):
    return transaction_service.create_transaction(user.uid, payload)


@router.put("/{doc_id}", response_model=TransactionOut, summary="거래 수정 (부분 수정)")
def update_transaction(doc_id: str, payload: TransactionUpdate, user: CurrentUser = Depends(require_consent)):
    try:
        return transaction_service.update_transaction(user.uid, doc_id, payload)
    except NotFoundError:
        raise HTTPException(404, "해당 거래를 찾을 수 없습니다.")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="거래 삭제")
def delete_transaction(doc_id: str, user: CurrentUser = Depends(require_consent)):
    try:
        transaction_service.delete_transaction(user.uid, doc_id)
    except NotFoundError:
        raise HTTPException(404, "해당 거래를 찾을 수 없습니다.")
