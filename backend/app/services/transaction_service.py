"""거래(지출) CRUD 비즈니스 로직. 모든 함수는 uid의 데이터만 다룬다."""
from datetime import datetime, timezone
from typing import Optional

from app.db import TRANSACTIONS, get_store, user_col
from app.schemas import TransactionCreate, TransactionUpdate
from app.services import summary_service


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _col(uid: str) -> str:
    return user_col(uid, TRANSACTIONS)


def list_transactions(uid: str, start: Optional[str] = None, end: Optional[str] = None,
                      limit: Optional[int] = None, descending: bool = True) -> list[dict]:
    filters = []
    if start:
        filters.append(("date", ">=", start))
    if end:
        filters.append(("date", "<=", end))
    rows = get_store().list(_col(uid), order_by="date", descending=descending, filters=filters, limit=limit)
    return [r for r in rows if _valid(r)]


def _valid(r: dict) -> bool:
    """이전 구조(date, value, memo)로 저장된 문서 등 형식이 다른 문서는 건너뛴다."""
    return isinstance(r.get("amount"), int) and bool(r.get("merchant")) and bool(r.get("category"))


def create_transaction(uid: str, payload: TransactionCreate, source: str = "manual",
                       category_by: str = "user") -> dict:
    item = get_store().add(_col(uid), {
        "date": payload.date.isoformat(),
        "amount": payload.amount,
        "merchant": payload.merchant,
        "category": payload.category,
        "memo": payload.memo,
        "source": source,
        "category_by": category_by,
        "created_at": _now(),
    })
    summary_service.invalidate_cache(uid)
    return item


def update_transaction(uid: str, doc_id: str, payload: TransactionUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
    if not changes:
        raise ValueError("수정할 필드가 없습니다.")
    if "category" in changes:
        changes["category_by"] = "user"  # 사람이 고친 분류 → 나중에 분류 규칙으로 기억
    item = get_store().update(_col(uid), doc_id, changes)
    summary_service.invalidate_cache(uid)
    return item


def delete_transaction(uid: str, doc_id: str) -> None:
    get_store().delete(_col(uid), doc_id)
    summary_service.invalidate_cache(uid)
