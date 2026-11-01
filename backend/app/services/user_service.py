"""사용자 프로필, 동의, 데이터 삭제, 체험용 샘플 데이터, 하루 사용량 제한."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth import CurrentUser
from app.config import settings
from app.db import TRANSACTIONS, USER_SUBCOLLECTIONS, USERS, get_store, user_col
from app.services import summary_service

KST = timezone(timedelta(hours=9))
SAMPLE_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "spending_2026.csv"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_profile(user: CurrentUser) -> dict:
    store = get_store()
    profile = store.get_or_none(USERS, user.uid)
    if profile is None:
        profile = {"created_at": _now()}
    # 로그인할 때마다 표시용 정보만 갱신 (최초 접속 시 문서 생성)
    store.set(USERS, user.uid, {**profile, "email": user.email, "name": user.name,
                                "is_anonymous": user.is_anonymous, "last_login_at": _now()})
    profile = store.get(USERS, user.uid)
    return {
        "uid": user.uid,
        "email": user.email,
        "name": user.name,
        "is_anonymous": user.is_anonymous,
        "consented": profile.get("consent_version") == settings.CONSENT_VERSION,
        "consent_version": settings.CONSENT_VERSION,
        "created_at": profile.get("created_at"),
    }


def give_consent(user: CurrentUser) -> dict:
    get_store().set(USERS, user.uid, {"consent_version": settings.CONSENT_VERSION, "consent_at": _now()})
    return get_profile(user)


def delete_all_data(user: CurrentUser) -> dict:
    """사용자의 모든 데이터와 프로필 문서를 삭제한다. Firebase 로그인 계정도 함께 삭제."""
    store = get_store()
    deleted = {name: store.delete_collection(user_col(user.uid, name)) for name in USER_SUBCOLLECTIONS}
    store.delete_doc(USERS, user.uid)
    summary_service.invalidate_cache(user.uid)
    if settings.DB_BACKEND != "memory":
        from firebase_admin import auth as fb_auth
        try:
            fb_auth.delete_user(user.uid)
        except Exception:
            pass  # 이미 없는 계정 등은 무시 (데이터 삭제가 핵심)
    return {"deleted": deleted}


def seed_demo_data(user: CurrentUser) -> dict:
    """'로그인 없이 체험하기'(익명) 사용자에게만 샘플 지출 데이터를 넣어준다. 이미 있으면 그대로."""
    store = get_store()
    col = user_col(user.uid, TRANSACTIONS)
    if store.list(col, limit=1):
        return {"seeded": 0}
    with SAMPLE_CSV.open(encoding="utf-8") as f:
        rows = [{"date": r["date"], "value": int(r["value"]), "memo": r["memo"]} for r in csv.DictReader(f)]
    n = store.batch_add(col, rows)
    summary_service.invalidate_cache(user.uid)
    return {"seeded": n}


class DailyLimitExceeded(Exception):
    pass


def consume_chat_quota(user: CurrentUser) -> int:
    """오늘(KST) 채팅 횟수를 1 늘리고 남은 횟수를 돌려준다. 한도 초과 시 예외."""
    store = get_store()
    today = datetime.now(KST).date().isoformat()
    usage = (store.get_or_none(USERS, user.uid) or {}).get("chat_usage") or {}
    count = usage.get("count", 0) if usage.get("date") == today else 0
    if count >= settings.DAILY_CHAT_LIMIT:
        raise DailyLimitExceeded()
    store.set(USERS, user.uid, {"chat_usage": {"date": today, "count": count + 1}})
    return settings.DAILY_CHAT_LIMIT - count - 1
