"""대화 기록 저장/조회 로직."""
from datetime import datetime, timezone
from typing import Optional

from app.db import CONVERSATIONS, get_store, user_col


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _title_from(messages: list[dict]) -> str:
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "새 대화")
    return first_user[:30] + ("…" if len(first_user) > 30 else "")


def _to_list_item(doc: dict) -> dict:
    return {
        "id": doc["id"], "title": doc.get("title", ""), "message_count": len(doc.get("messages", [])),
        "created_at": doc.get("created_at", ""), "updated_at": doc.get("updated_at", ""),
    }


def create_conversation(uid: str, messages: list[dict], title: Optional[str] = None) -> dict:
    now = _now()
    return get_store().add(user_col(uid, CONVERSATIONS), {
        "title": title or _title_from(messages), "messages": messages, "created_at": now, "updated_at": now,
    })


def append_messages(uid: str, conv_id: str, new_messages: list[dict]) -> dict:
    store = get_store()
    col = user_col(uid, CONVERSATIONS)
    conv = store.get(col, conv_id)
    return store.update(col, conv_id, {
        "messages": conv.get("messages", []) + new_messages, "updated_at": _now(),
    })


def list_conversations(uid: str) -> list[dict]:
    docs = get_store().list(user_col(uid, CONVERSATIONS), order_by="updated_at", descending=True)
    return [_to_list_item(d) for d in docs]


def get_conversation(uid: str, conv_id: str) -> dict:
    doc = get_store().get(user_col(uid, CONVERSATIONS), conv_id)
    return {**_to_list_item(doc), "messages": doc.get("messages", [])}


def delete_conversation(uid: str, conv_id: str) -> None:
    get_store().delete(user_col(uid, CONVERSATIONS), conv_id)
