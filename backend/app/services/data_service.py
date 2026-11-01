"""데이터 CRUD 비즈니스 로직."""
from typing import Optional

from app.db import TRANSACTIONS, get_store, user_col
from app.schemas import DataCreate, DataUpdate
from app.services import summary_service


def list_data(uid: str, start: Optional[str] = None, end: Optional[str] = None,
              limit: Optional[int] = None, descending: bool = True) -> list[dict]:
    filters = []
    if start:
        filters.append(("date", ">=", start))
    if end:
        filters.append(("date", "<=", end))
    return get_store().list(user_col(uid, TRANSACTIONS), order_by="date", descending=descending, filters=filters, limit=limit)


def create_data(uid: str, payload: DataCreate) -> dict:
    item = get_store().add(user_col(uid, TRANSACTIONS), {"date": payload.date.isoformat(), "value": payload.value, "memo": payload.memo})
    summary_service.invalidate_cache(uid)
    return item


def update_data(uid: str, doc_id: str, payload: DataUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    if not changes:
        raise ValueError("수정할 필드가 없습니다.")
    item = get_store().update(user_col(uid, TRANSACTIONS), doc_id, changes)
    summary_service.invalidate_cache(uid)
    return item


def delete_data(uid: str, doc_id: str) -> None:
    get_store().delete(user_col(uid, TRANSACTIONS), doc_id)
    summary_service.invalidate_cache(uid)
