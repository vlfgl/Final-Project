"""월 절약 목표: 저장(이월·변경 이력) + 진행률·페이스 계산 + 추천.

저장 구조: users/{uid}/goals/{YYYY-MM}
  total_budget        월 총예산(원)
  category_limits     [{category, limit}] 최대 3개
  history             [{changed_at, total_budget, category_limits}]  — 바뀌기 전 값들
  created_at, updated_at

규칙
- 목표 문서가 없는 달은 가장 최근의 이전 달 목표를 '이어서' 보여준다(읽기만, 저장은 사용자가 할 때).
- 지난 달 목표는 수정할 수 없다 (달성 기록이 바뀌지 않도록).
- 계산(진행률·페이스·추천)은 모두 코드로 한다.
"""
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from app.db import GOALS, get_store, user_col
from app.services import summary_service
from app.services.transaction_service import list_transactions

# 줄이기 어려운 고정성 지출 → 추천 카테고리 한도에서 제외
FIXED_CATEGORIES = {"주거·통신", "구독", "교육", "의료·건강"}


class GoalError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _col(uid: str) -> str:
    return user_col(uid, GOALS)


def _days_in_month(month: str) -> int:
    y, m = map(int, month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def _month_range(month: str) -> tuple[str, str]:
    return f"{month}-01", f"{month}-{_days_in_month(month):02d}"


def _prev_month(month: str, n: int = 1) -> str:
    y, m = map(int, month.split("-"))
    m -= n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def current_month() -> str:
    return summary_service.today_kst().strftime("%Y-%m")


# ---------------------------------------------------------------- 저장/조회
def get_goal(uid: str, month: str) -> tuple[Optional[dict], Optional[str]]:
    """(목표, 이어받은 달). 이 달 문서가 없으면 가장 최근 이전 달 목표를 이어받는다."""
    store = get_store()
    own = store.get_or_none(_col(uid), month)
    if own:
        return own, None
    earlier = [g for g in store.list(_col(uid)) if g["id"] < month]
    if not earlier:
        return None, None
    latest = max(earlier, key=lambda g: g["id"])
    return latest, latest["id"]


def save_goal(uid: str, month: str, total_budget: int, category_limits: list[dict]) -> dict:
    if month < current_month():
        raise GoalError("지난 달 목표는 수정할 수 없어요.")
    cats = [c["category"] for c in category_limits]
    if len(cats) != len(set(cats)):
        raise GoalError("같은 카테고리를 두 번 넣을 수 없어요.")
    if any(c["limit"] > total_budget for c in category_limits):
        raise GoalError("카테고리 한도는 월 총예산보다 클 수 없어요.")

    store = get_store()
    now = _now()
    old = store.get_or_none(_col(uid), month)
    history = (old or {}).get("history", [])
    if old and (old.get("total_budget") != total_budget or old.get("category_limits") != category_limits):
        history = history + [{"changed_at": now, "total_budget": old.get("total_budget"),
                              "category_limits": old.get("category_limits", [])}]
    store.set(_col(uid), month, {
        "total_budget": total_budget,
        "category_limits": category_limits,
        "history": history,
        "created_at": (old or {}).get("created_at", now),
        "updated_at": now,
    }, merge=False)
    return store.get(_col(uid), month)


def delete_goal(uid: str, month: str) -> None:
    if month < current_month():
        raise GoalError("지난 달 목표는 삭제할 수 없어요.")
    get_store().delete_doc(_col(uid), month)


# ---------------------------------------------------------------- 진행률·페이스
def _status(spent: int, limit: int, projected: Optional[int]) -> str:
    if spent > limit:
        return "over"        # 이미 초과
    if projected is not None and projected > limit:
        return "warning"     # 이 페이스면 초과 예상
    return "good"


def progress(uid: str, month: str, goal: Optional[dict]) -> dict:
    start, end = _month_range(month)
    rows = list_transactions(uid, start=start, end=end)
    spent = sum(r["amount"] for r in rows)
    by_cat = defaultdict(int)
    for r in rows:
        by_cat[r["category"]] += r["amount"]

    days = _days_in_month(month)
    cur = current_month()
    if month < cur:
        phase, elapsed = "past", days
    elif month > cur:
        phase, elapsed = "future", 0
    else:
        phase, elapsed = "current", summary_service.today_kst().day

    def proj(amount: int) -> Optional[int]:
        if phase == "past":
            return amount
        if phase == "future" or elapsed < 3:  # 월초 2일까지는 예측이 의미 없음
            return None
        return round(amount / elapsed * days)

    result = {
        "month": month, "phase": phase, "days_in_month": days, "elapsed_days": elapsed,
        "spent": spent, "projected": proj(spent),
        "pace_ratio": round(elapsed / days, 3),  # 오늘까지 '써도 되는' 비율 (막대 위 표시용)
        "total": None, "categories": [],
    }
    if not goal:
        return result
    budget = goal["total_budget"]
    result["total"] = {
        "budget": budget, "spent": spent, "remaining": budget - spent,
        "used_pct": round(spent / budget * 100, 1) if budget else None,
        "projected": proj(spent),
        "status": _status(spent, budget, proj(spent)),
        # 남은 날 하루에 쓸 수 있는 금액
        "daily_allowance": round((budget - spent) / (days - elapsed + (1 if phase == "current" else 0)))
        if phase != "past" and budget > spent else 0,
    }
    for c in goal.get("category_limits", []):
        s = by_cat.get(c["category"], 0)
        result["categories"].append({
            "category": c["category"], "limit": c["limit"], "spent": s,
            "used_pct": round(s / c["limit"] * 100, 1) if c["limit"] else None,
            "projected": proj(s), "status": _status(s, c["limit"], proj(s)),
        })
    return result


# ---------------------------------------------------------------- 추천
def _round_to(x: float, unit: int) -> int:
    return max(unit, int(round(x / unit)) * unit)


def _ceil_to(x: float, unit: int) -> int:
    return max(unit, -(-int(x) // unit) * unit)


def spent_so_far(uid: str, month: str) -> tuple[int, dict]:
    """해당 달에 지금까지 쓴 총액과 카테고리별 금액."""
    start, end = _month_range(month)
    by_cat = defaultdict(int)
    for r in list_transactions(uid, start=start, end=end):
        by_cat[r["category"]] += r["amount"]
    return sum(by_cat.values()), dict(by_cat)


def suggest(uid: str, month: str) -> dict:
    """최근 3개 '완료된' 달 평균 기준 추천: 총예산 -10%, 변동 지출 상위 3개 카테고리 -15%.
    진행 중인 달이면 이미 쓴 금액보다 낮은 한도는 지킬 수 없으므로, 쓴 금액의 110%(5천 원 단위 올림)보다 낮게 잡지 않는다."""
    months = [_prev_month(month, i) for i in (1, 2, 3)]
    start, _ = _month_range(months[-1])
    _, end = _month_range(months[0])
    rows = list_transactions(uid, start=start, end=end)
    have = sorted({r["date"][:7] for r in rows})
    if not have:
        return {"available": False, "basis_months": [], "reason": "최근 3개월 지출 데이터가 없어요."}
    n = len(have)
    total_avg = sum(r["amount"] for r in rows) / n
    by_cat = defaultdict(int)
    for r in rows:
        by_cat[r["category"]] += r["amount"]
    flexible = sorted(((c, v / n) for c, v in by_cat.items() if c not in FIXED_CATEGORIES and c != "기타"),
                      key=lambda x: x[1], reverse=True)[:3]
    in_progress = month == current_month()
    spent_total, spent_cat = spent_so_far(uid, month) if in_progress else (0, {})

    def floor_by_spent(value: int, spent: int, unit: int) -> tuple[int, bool]:
        if in_progress and spent and value < spent * 1.1:
            return _ceil_to(spent * 1.1, unit), True
        return value, False

    total_budget, total_adj = floor_by_spent(_round_to(total_avg * 0.9, 10000), spent_total, 10000)
    limits = []
    for c, avg in flexible:
        limit, adj = floor_by_spent(_round_to(avg * 0.85, 5000), spent_cat.get(c, 0), 5000)
        item = {"category": c, "average": round(avg), "limit": limit}
        if in_progress:
            item["spent_so_far"] = spent_cat.get(c, 0)
            item["adjusted_for_spent"] = adj
        limits.append(item)
    out = {
        "available": True,
        "basis_months": have,
        "total_average": round(total_avg),
        "total_budget": total_budget,
        "category_limits": limits,
        "rule": "최근 지출 평균에서 총예산은 10%, 줄이기 쉬운 상위 3개 카테고리는 15% 줄인 값. "
                "진행 중인 달은 이미 쓴 금액의 110%보다 낮게 잡지 않음(adjusted_for_spent=true인 항목)",
    }
    if in_progress:
        out["spent_so_far_total"] = spent_total
        out["total_adjusted_for_spent"] = total_adj
    return out


# ---------------------------------------------------------------- 채팅 프롬프트용
def prompt_text(uid: str) -> str:
    month = current_month()
    goal, inherited = get_goal(uid, month)
    if not goal:
        return "- 이번 달 절약 목표: 아직 없음"
    p = progress(uid, month, goal)
    t = p["total"]
    lines = [f"- 이번 달({month}) 절약 목표: 총예산 {t['budget']:,}원"
             + (f" (지난 {inherited} 목표를 이어서 적용 중)" if inherited else "")
             + f", 현재 {t['spent']:,}원 사용({t['used_pct']}%), {p['elapsed_days']}/{p['days_in_month']}일 경과"
             + (f", 이 페이스면 월말 {t['projected']:,}원" if t["projected"] is not None else "")
             + {"good": " → 목표 안쪽", "warning": " → 초과 예상", "over": " → 이미 초과"}[t["status"]]]
    for c in p["categories"]:
        lines.append(f"  · {c['category']} 한도 {c['limit']:,}원 중 {c['spent']:,}원 사용({c['used_pct']}%)"
                     + {"good": "", "warning": ", 초과 예상", "over": ", 이미 초과"}[c["status"]])
    return "\n".join(lines)
