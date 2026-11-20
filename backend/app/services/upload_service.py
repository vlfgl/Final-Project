"""이미지 인식 결과 후처리 + 일괄 저장.

AI는 '읽기'만 하고, 아래 판단은 코드가 한다 (계산·규칙은 코드, 해석은 AI):
- 연도 보정: 오늘보다 미래 날짜 → 1년 전으로 (연도 없는 캡처를 AI가 잘못 추정한 경우)
- 취소 거래: 기본 체크 해제
- 중복: 이미 저장된 거래와 날짜·금액·가맹점이 같으면 표시 + 기본 체크 해제
- 분류 규칙(메모리): 사용자가 직접 고친 가맹점 분류가 있으면 AI 분류 대신 그걸 적용
"""
import re
from difflib import SequenceMatcher
from datetime import date, timedelta
from typing import Optional

from app.auth import CurrentUser
from app.db import TRANSACTIONS, get_store, user_col
from app.schemas import CATEGORIES, BulkItem
from app.services import summary_service, vision_service
from app.services.transaction_service import _now, list_transactions

_STRIP = re.compile(r"\(주\)|㈜|주식회사|\s+|[·.\-_/()]")


def norm_merchant(name: str) -> str:
    return _STRIP.sub("", (name or "").lower())


def dup_key(d: Optional[str], amount: int, merchant: str) -> tuple:
    return (d, int(amount), norm_merchant(merchant))


def _similar_exists(d: str, amount: int, merchant: str, existing_keys: set) -> bool:
    """같은 날짜·금액에 이름이 비슷한 거래(인식 오타를 사용자가 고쳐 저장한 경우 등)가 있는지."""
    name = norm_merchant(merchant)
    for (ed, ea, em) in existing_keys:
        if ed == d and ea == amount and em and name:
            if em in name or name in em or SequenceMatcher(None, em, name).ratio() >= 0.6:
                return True
    return False


def category_rules(uid: str) -> dict[str, str]:
    """사용자가 직접 고친(category_by=user) 거래에서 '가맹점 → 카테고리' 규칙을 만든다. 최근 것이 우선."""
    rules: dict[str, tuple[str, str]] = {}
    for t in list_transactions(uid, descending=False):
        if t.get("category_by") == "user" and t.get("source") != "sample":
            key = norm_merchant(t["merchant"])
            stamp = t.get("created_at", "")
            if key and (key not in rules or stamp >= rules[key][1]):
                rules[key] = (t["category"], stamp)
    return {k: v[0] for k, v in rules.items()}


WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

_RE_YMD = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
_RE_YM_KO = re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월")
_RE_MD_KO = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_RE_MD_NUM = re.compile(r"(?<![\d:])(\d{1,2})\s*[./]\s*(\d{1,2})(?![\d:])")
_RE_D_KO = re.compile(r"(\d{1,2})\s*일")
_RE_WD = re.compile(r"([월화수목금토일])\s*(?:요일|\)|）)")


def parse_date_text(text: Optional[str], today: date) -> Optional[dict]:
    """화면에 보인 날짜 글자 → {year, month, day, weekday}. 글자에 없는 값은 None.

    모델이 칸(year/month)에 '보이지 않는 값'을 채워 넣는 경우가 있어서, 글자를 코드가 다시 읽는다.
    읽을 수 없는 글자면 None을 돌려주고, 그때는 모델이 준 칸 값을 쓴다.
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    if t.startswith("오늘"):
        return {"year": today.year, "month": today.month, "day": today.day, "weekday": None}
    if t.startswith("어제"):
        d = today - timedelta(days=1)
        return {"year": d.year, "month": d.month, "day": d.day, "weekday": None}
    wm = _RE_WD.search(t)
    wd = wm.group(1) if wm else None
    out = {"year": None, "month": None, "day": None, "weekday": wd}
    if m := _RE_YMD.search(t):
        out.update(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))
    elif m := _RE_MD_KO.search(t):
        out.update(month=int(m.group(1)), day=int(m.group(2)))
        if y := _RE_YM_KO.search(t):
            out["year"] = int(y.group(1))
    elif m := _RE_MD_NUM.search(t):
        out.update(month=int(m.group(1)), day=int(m.group(2)))
    elif m := _RE_D_KO.search(t):
        out["day"] = int(m.group(1))
    else:
        return None
    if out["month"] is not None and not 1 <= out["month"] <= 12:
        return None
    if out["day"] is not None and not 1 <= out["day"] <= 31:
        return None
    return out

def resolve_date(year: Optional[int], month: Optional[int], day: Optional[int], today: date,
                 weekday: Optional[str] = None) -> tuple[Optional[str], list[str]]:
    """이미지에 보인 연·월·일·요일 → 날짜. 규칙(코드)으로 정해서 같은 캡처는 항상 같은 날짜가 된다.

    - 연·월·일 모두 보임   → 그대로 (1년 넘게 지났거나 미래면 확인 표시)
    - 연도 없음           → 오늘 이전의 가장 가까운 날짜. 요일이 보이면 요일까지 맞는 날짜
    - 월도 없음(일+요일)  → '그 일자이면서 그 요일'인 가장 가까운 과거 날짜 (최근 3년 안)
    - 그 외(일만, 날짜 없음) → None (사용자가 직접 입력)
    """
    wd = WEEKDAYS.index(weekday) if weekday in WEEKDAYS else None
    if not day:
        return None, ["날짜를 읽지 못했어요. 직접 입력해 주세요."]
    notes: list[str] = []
    if year and month:
        try:
            d = date(year, month, day)
        except ValueError:
            return None, ["날짜가 올바르지 않아요. 직접 입력해 주세요."]
        if d > today:
            notes.append("미래 날짜예요. 확인해 주세요.")
        elif (today - d).days > 365:
            notes.append("1년 이상 지난 거래예요. 연도를 확인해 주세요.")
        return d.isoformat(), notes
    if not month and wd is None:
        return None, ["월을 알 수 없어요. 날짜를 직접 입력해 주세요."]
    # 오늘부터 과거로 거슬러 올라가며 조건에 맞는 첫 날짜
    y, m = today.year, today.month
    for _ in range(37):  # 최근 3년 (윤년 2/29 포함 가능 범위)
        if month is None or m == month:
            try:
                d = date(y, m, day)
            except ValueError:
                d = None
            if d and d <= today and (wd is None or d.weekday() == wd):
                return d.isoformat(), notes
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return None, ["날짜를 확정할 수 없어요. 직접 입력해 주세요."]


def postprocess(raw: dict, today: date, existing_keys: set, rules: dict[str, str]) -> dict:
    items = []
    seen = set()
    for t in raw.get("transactions", []):
        amount = int(t.get("amount") or 0)
        merchant = (t.get("merchant") or "").strip()[:100]
        if amount <= 0 or not merchant:
            continue
        parsed = parse_date_text(t.get("date_text"), today)
        src = parsed or {k: t.get(k) for k in ("year", "month", "day", "weekday")}
        d, notes = resolve_date(src["year"], src["month"], src["day"], today, src["weekday"])
        if d and not src["month"]:
            notes.append("화면에 월이 없어 요일이 맞는 가장 가까운 과거 날짜로 정했어요. 확인해 주세요.")
        elif d and src["year"] and src["month"] and src["weekday"] in WEEKDAYS \
                and date.fromisoformat(d).weekday() != WEEKDAYS.index(src["weekday"]):
            notes.append("날짜와 요일이 맞지 않아요. 날짜를 확인해 주세요.")
        category = t.get("category") if t.get("category") in CATEGORIES else "기타"
        category_by = "ai"
        rule = rules.get(norm_merchant(merchant))
        if rule and rule != category:
            category, category_by = rule, "rule"
            notes.append("이전에 직접 고친 분류를 적용했어요.")
        status = t.get("status") if t.get("status") in ("spent", "income", "canceled") else "spent"
        low = t.get("confidence") == "low"
        key = dup_key(d, amount, merchant)
        exact = d is not None and (key in existing_keys or key in seen)
        similar = not exact and d is not None and _similar_exists(d, amount, merchant, existing_keys)
        duplicate = exact or similar
        seen.add(key)
        if status == "canceled":
            notes.append("화면에 '취소'로 표시된 거래예요.")
        if status == "income":
            notes.append("들어온 돈(입금·환불)이라 지출에서 뺐어요.")
        if exact:
            notes.append("이미 있는 거래와 같아요.")
        if similar:
            notes.append("날짜·금액이 같고 이름이 비슷한 거래가 이미 있어요.")
        if low:
            notes.append("흐릿하게 읽혔어요. 값을 확인해 주세요.")
        items.append({
            "date": d, "amount": amount, "merchant": merchant, "category": category, "category_by": category_by,
            "status": status, "low_confidence": low, "duplicate": duplicate,
            "include": status == "spent" and not duplicate and d is not None, "notes": notes,
        })
    image_type = raw.get("image_type")
    if image_type not in ("card_statement", "transaction_detail", "receipt", "other"):
        image_type = "other"
    return {"image_type": image_type, "items": items}


def extract_from_image(user: CurrentUser, data_url: str) -> dict:
    today = summary_service.today_kst()
    raw = vision_service.extract(data_url, today)
    # 중복 비교 대상: 추출된 날짜 범위의 기존 거래만 조회 (읽기 비용 절약)
    result = postprocess(raw, today, set(), {})  # 날짜 범위를 먼저 알아내기 위한 1차 처리
    dates = sorted(i["date"] for i in result["items"] if i["date"])
    existing = set()
    if dates:
        for t in list_transactions(user.uid, start=dates[0], end=dates[-1]):
            existing.add(dup_key(t["date"], t["amount"], t["merchant"]))
    return postprocess(raw, today, existing, category_rules(user.uid))


def bulk_create(uid: str, items: list[BulkItem]) -> int:
    now = _now()
    docs = [{
        "date": i.date.isoformat(), "amount": i.amount, "merchant": i.merchant, "category": i.category,
        "memo": i.memo, "source": i.source, "category_by": i.category_by, "created_at": now,
    } for i in items]
    n = get_store().batch_add(user_col(uid, TRANSACTIONS), docs)
    summary_service.invalidate_cache(uid)
    return n
