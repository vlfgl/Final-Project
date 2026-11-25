"""거래 데이터 분석 → 요약 생성 (대시보드 + 프롬프트 주입용).

요약은 채팅마다 필요하므로 사용자별 메모리 캐시를 두고, 데이터가 바뀌면(CRUD) 무효화한다.
→ 매 채팅마다 Firestore 전체 문서를 다시 읽는 비용(읽기 횟수)을 줄인다.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Optional

from app.db import TRANSACTIONS, get_store, user_col

_cache: dict[str, tuple] = {}
KST = timezone(timedelta(hours=9))
MIN_DAYS_FOR_PROJECTION = 7


def today_kst() -> date:
    return datetime.now(KST).date()
_lock = Lock()


def invalidate_cache(uid: str) -> None:
    with _lock:
        _cache.pop(uid, None)


def get_summary(uid: str) -> dict:
    today = today_kst()
    with _lock:
        hit = _cache.get(uid)
        if hit and hit[0] == today:  # 날짜가 바뀌면 '이번 달'·'최근 30일'이 달라지므로 다시 계산
            return hit[1]
    from app.services.transaction_service import list_transactions
    rows = list_transactions(uid, descending=False)
    result = build_summary(rows, today)
    with _lock:
        _cache[uid] = (today, result)
    return result


def _pct(a: float, b: float) -> Optional[float]:
    return round((a - b) / b * 100, 1) if b else None


def _trend_label(change: Optional[float], threshold: float = 5.0) -> str:
    if change is None:
        return "판단 불가"
    if change > threshold:
        return "증가"
    if change < -threshold:
        return "감소"
    return "유지"


def build_summary(rows: list[dict], today: Optional[date] = None) -> dict:
    """today: '이번 달'과 '최근 30일'의 기준일 (기본: 오늘, KST)."""
    today = today or today_kst()
    if not rows:
        return {
            "period": "데이터 없음", "count": 0,
            "metrics": {"total": 0, "average": 0, "daily_average": 0, "monthly_average": 0, "max": {}, "min": {}},
            "trend": "판단 불가", "current_month": {}, "monthly_totals": {}, "monthly_categories": {}, "categories": [],
        }

    rows = sorted(rows, key=lambda r: r["date"])
    values = [int(r["amount"]) for r in rows]
    total = sum(values)
    first, last = date.fromisoformat(rows[0]["date"]), date.fromisoformat(rows[-1]["date"])
    days = (last - first).days + 1

    daily = defaultdict(int)
    monthly = defaultdict(int)
    by_cat = defaultdict(int)
    month_cat = defaultdict(lambda: defaultdict(int))  # 월별 카테고리 합계 (도넛 차트 + 프롬프트)
    for r in rows:
        month_cat[r["date"][:7]][r.get("category") or "기타"] += int(r["amount"])
        daily[r["date"]] += int(r["amount"])
        monthly[r["date"][:7]] += int(r["amount"])
        by_cat[r.get("category") or "기타"] += int(r["amount"])

    max_row = max(rows, key=lambda r: r["amount"])
    min_row = min(rows, key=lambda r: r["amount"])

    # 최근 30일 vs 직전 30일 (오늘 기준)
    def window_sum(end: date, length: int) -> int:
        start = end - timedelta(days=length - 1)
        return sum(v for d, v in daily.items() if start.isoformat() <= d <= end.isoformat())

    recent = window_sum(today, 30)
    previous = window_sum(today - timedelta(days=30), 30)
    change = _pct(recent, previous)
    trend = f"{_trend_label(change)} (최근 30일 {recent:,}원, 직전 30일 대비 {change:+.1f}%)" if change is not None \
        else "판단 불가 (비교 기간 데이터 부족)"

    # 이번 달(오늘 기준): 경과 일수 기준 일평균으로 월말 예상치 계산
    cur_key = today.strftime("%Y-%m")
    cur_total = monthly[cur_key]  # defaultdict: 이번 달 거래가 없으면 0으로 들어감
    full_months = {k: v for k, v in monthly.items() if k != cur_key}
    monthly_avg = sum(full_months.values()) / len(full_months) if full_months else cur_total
    elapsed = today.day
    projected = round(cur_total / elapsed * _days_in_month(today))

    # 지난달 같은 기간(1일 ~ 오늘 날짜): 진행 중인 달을 끝난 달 전체와 비교하면 무조건 '감소'로 나온다
    prev_last = today.replace(day=1) - timedelta(days=1)
    prev_key = prev_last.strftime("%Y-%m")
    prev_end = prev_last.replace(day=min(elapsed, prev_last.day)).isoformat()
    prev_same = sum(v for d, v in daily.items() if d.startswith(prev_key) and d <= prev_end)
    has_prev = prev_key in monthly

    top = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)

    # 카테고리별 이번 달 vs 지난달 같은 기간 (소비 요약의 '지난달 대비' 목록)
    cur_cat, prev_cat = defaultdict(int), defaultdict(int)
    for r in rows:
        d, c = r["date"], r.get("category") or "기타"
        if d.startswith(cur_key) and d <= today.isoformat():
            cur_cat[c] += int(r["amount"])
        elif d.startswith(prev_key) and d <= prev_end:
            prev_cat[c] += int(r["amount"])
    category_compare = [
        {"category": c, "current": cur_cat[c], "prev_same_period": prev_cat[c] if has_prev else None,
         "pct": _pct(cur_cat[c], prev_cat[c]) if has_prev and prev_cat[c] else None}
        for c in sorted(set(cur_cat) | set(prev_cat), key=lambda c: (cur_cat[c], prev_cat[c]), reverse=True)
    ]

    return {
        "period": f"{first.isoformat()} ~ {last.isoformat()}",
        "count": len(rows),
        "metrics": {
            "total": total,
            "average": round(total / len(rows)),
            "daily_average": round(total / days),
            "monthly_average": round(monthly_avg),
            "max": {"date": max_row["date"], "amount": max_row["amount"], "merchant": max_row.get("merchant", ""),
                    "category": max_row.get("category", "")},
            "min": {"date": min_row["date"], "amount": min_row["amount"], "merchant": min_row.get("merchant", ""),
                    "category": min_row.get("category", "")},
        },
        "trend": trend,
        "current_month": {
            "month": cur_key,
            "total": cur_total,
            "elapsed_days": elapsed,
            "projected_total": projected,
            # 비교하지 않는 경우: 비교할 완료된 달이 없을 때, 월초(7일 미만)라 예상치가 불안정할 때
            "vs_monthly_average_pct": _pct(projected, monthly_avg) if full_months and elapsed >= MIN_DAYS_FOR_PROJECTION else None,
            "projection_ready": elapsed >= MIN_DAYS_FOR_PROJECTION,
            "prev_month": prev_key,
            "prev_same_period_days": min(elapsed, prev_last.day),
            "prev_same_period_total": prev_same if has_prev else None,
            "vs_prev_same_period_pct": _pct(cur_total, prev_same) if has_prev and prev_same else None,
            "category_compare": category_compare,
        },
        "monthly_totals": dict(sorted(monthly.items())),
        "monthly_categories": {
            mk: [{"category": c, "total": v, "share_pct": round(v / sum(cats.values()) * 100, 1)}
                 for c, v in sorted(cats.items(), key=lambda x: x[1], reverse=True)]
            for mk, cats in sorted(month_cat.items())
        },
        "categories": [
            {"category": c, "total": v, "share_pct": round(v / total * 100, 1)} for c, v in top
        ],
    }


def _days_in_month(d: date) -> int:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).day


def to_prompt_text(s: dict) -> str:
    """요약 dict → 시스템 프롬프트에 넣을 짧은 텍스트 (토큰 절약)."""
    if not s["count"]:
        return "- 저장된 지출 데이터가 없습니다."
    m, cm = s["metrics"], s["current_month"]
    monthly = ", ".join(f"{k}: {v:,}원" for k, v in s["monthly_totals"].items())
    cats = ", ".join(f"{c['category']} {c['total']:,}원({c['share_pct']}%)" for c in s["categories"])
    return "\n".join([
        f"- 데이터 기간: {s['period']}",
        f"- 총 레코드: {s['count']}건",
        f"- 총 지출: {m['total']:,}원 / 월평균 {m['monthly_average']:,}원 / 일평균 {m['daily_average']:,}원 / 건당 평균 {m['average']:,}원",
        f"- 최대 지출: {m['max']['date']} {m['max']['amount']:,}원 ({m['max']['merchant']}, {m['max']['category']})",
        f"- 최근 트렌드: {s['trend']}",
        f"- 이번 달({cm['month']}): {cm['elapsed_days']}일 경과, 현재 {cm['total']:,}원, 월말 예상 {cm['projected_total']:,}원 "
        + (f"(월평균 대비 {cm['vs_monthly_average_pct']:+}%)" if cm["vs_monthly_average_pct"] is not None
           else "(월초이거나 이전 달 데이터가 없어 월평균과 비교하지 않음)"),
        f"- 월별 지출: {monthly}",
        f"- 카테고리별 전체 지출: {cats}",
        *[f"- {mk} 카테고리별 지출: " + ", ".join(f"{c['category']} {c['total']:,}원" for c in items)
          for mk, items in list(s.get("monthly_categories", {}).items())[-3:]],  # 최근 3개월
    ])
