"""AI Agent가 '스스로 골라 호출하는' 도구들.

설계 원칙
- 어떤 도구를 언제, 어떤 인자로 부를지는 모델이 정한다. 코드에는 "이 질문이면 이 도구" 같은 분기가 없다.
- 도구는 계산된 숫자(합계·건수·증감률)를 돌려준다. 모델은 이 숫자만 근거로 답한다 (계산은 코드, 해석은 AI).
- 모든 도구는 로그인한 사용자(uid)의 데이터만 본다. uid는 모델이 아니라 서버가 넣는다.
- 데이터를 바꾸는 도구는 없다. propose_goal은 '제안'만 만들고, 저장은 사용자가 화면에서 직접 한다.
- 인자는 Pydantic으로 검증한다. 잘못된 인자는 예외 대신 {"error": ...}로 돌려줘 모델이 고쳐서 다시 부르게 한다.
"""
import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.schemas import CATEGORIES
from app.services import goal_service, summary_service
from app.services.transaction_service import list_transactions
from app.services.upload_service import norm_merchant

MONTH_RE = r"^\d{4}-(0[1-9]|1[0-2])$"
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


# ---------------------------------------------------------------- 공통 계산
def _month_bounds(month: str) -> tuple[str, str]:
    return goal_service._month_range(month)


def _rows(uid: str, start: str, end: str) -> list[dict]:
    return list_transactions(uid, start=start, end=end, descending=False)


def _cat_totals(rows: list[dict]) -> dict[str, int]:
    out = defaultdict(int)
    for r in rows:
        out[r["category"]] += r["amount"]
    return dict(out)


def _top_merchants(rows: list[dict], n: int = 5) -> list[dict]:
    agg = defaultdict(lambda: [0, 0, ""])
    for r in rows:
        k = norm_merchant(r["merchant"])
        agg[k][0] += 1
        agg[k][1] += r["amount"]
        agg[k][2] = agg[k][2] or r["merchant"]
    top = sorted(agg.values(), key=lambda x: x[1], reverse=True)[:n]
    return [{"merchant": m, "count": c, "total": t} for c, t, m in top]


def _pct(a: float, b: float) -> Optional[float]:
    return round((a - b) / b * 100, 1) if b else None


def _projection(month: str) -> tuple[str, int, int]:
    """(phase, elapsed_days, days_in_month) — 이번 달이면 경과 일수 기준 월말 예상에 쓴다."""
    days = goal_service._days_in_month(month)
    cur = goal_service.current_month()
    if month < cur:
        return "past", days, days
    if month > cur:
        return "future", 0, days
    return "current", summary_service.today_kst().day, days


def _first_days_bounds(month: str, day: int) -> tuple[str, str]:
    """그 달 1일 ~ day일 (그 달 길이를 넘지 않게). 진행 중인 달과 '같은 기간'을 비교할 때 쓴다."""
    start, _ = _month_bounds(month)
    d = min(day, goal_service._days_in_month(month))
    return start, f"{month}-{d:02d}"


# ---------------------------------------------------------------- 인자 모델 + 구현
class SearchArgs(BaseModel):
    start_date: str = Field(..., pattern=DATE_RE)
    end_date: str = Field(..., pattern=DATE_RE)
    merchant_query: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = None
    min_amount: Optional[int] = Field(None, ge=0)
    limit: Optional[int] = Field(None, ge=1, le=20)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v):
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"category는 다음 중 하나여야 합니다: {', '.join(CATEGORIES)}")
        return v


def search_transactions(uid: str, a: SearchArgs) -> tuple[dict, str]:
    if a.start_date > a.end_date:
        raise ValueError("start_date가 end_date보다 늦습니다.")
    rows = _rows(uid, a.start_date, a.end_date)
    if a.merchant_query:
        q = norm_merchant(a.merchant_query)
        rows = [r for r in rows if q and q in norm_merchant(r["merchant"])]
    if a.category:
        rows = [r for r in rows if r["category"] == a.category]
    if a.min_amount:
        rows = [r for r in rows if r["amount"] >= a.min_amount]
    total = sum(r["amount"] for r in rows)
    items = sorted(rows, key=lambda r: r["date"], reverse=True)[: a.limit or 10]
    result = {
        "period": f"{a.start_date} ~ {a.end_date}",
        "filters": {"merchant_query": a.merchant_query, "category": a.category, "min_amount": a.min_amount},
        "count": len(rows), "total": total,
        "average_per_item": round(total / len(rows)) if rows else 0,
        "top_merchants": _top_merchants(rows),
        "recent_items": [{"date": r["date"], "merchant": r["merchant"], "amount": r["amount"],
                          "category": r["category"]} for r in items],
    }
    label = " · ".join(x for x in [a.merchant_query, a.category] if x) or "전체"
    return result, f"{a.start_date}~{a.end_date} {label}: {len(rows)}건, {total:,}원"


class MonthArgs(BaseModel):
    month: str = Field(..., pattern=MONTH_RE)


def get_monthly_summary(uid: str, a: MonthArgs) -> tuple[dict, str]:
    start, end = _month_bounds(a.month)
    rows = _rows(uid, start, end)
    total = sum(r["amount"] for r in rows)
    prev = goal_service._prev_month(a.month)
    ps, pe = _month_bounds(prev)
    prev_total = sum(r["amount"] for r in _rows(uid, ps, pe))
    phase, elapsed, days = _projection(a.month)
    prev_info = {"month": prev, "total": prev_total, "change_pct": _pct(total, prev_total)}
    if phase == "current":  # 20일치를 한 달 전체와 비교하면 무조건 '감소'로 나온다 → 같은 기간으로 비교
        same = sum(r["amount"] for r in _rows(uid, *_first_days_bounds(prev, elapsed)))
        prev_info = {"month": prev, "total": prev_total, "same_period_total": same,
                     "change_pct": _pct(total, same),
                     "basis": f"두 달 모두 1~{elapsed}일 기준으로 비교한 변화율"}
    cats = sorted(_cat_totals(rows).items(), key=lambda x: x[1], reverse=True)
    result = {
        "month": a.month, "phase": phase, "elapsed_days": elapsed, "days_in_month": days,
        "total": total, "count": len(rows),
        "projected_month_end": round(total / elapsed * days) if phase == "current" and elapsed >= 3 else None,
        "previous_month": prev_info,
        "categories": [{"category": c, "total": v, "share_pct": round(v / total * 100, 1)} for c, v in cats],
        "top_merchants": _top_merchants(rows),
    }
    return result, f"{a.month}: 총 {total:,}원 ({len(rows)}건)"


class CompareArgs(BaseModel):
    month_a: str = Field(..., pattern=MONTH_RE, description="기준(이전) 달")
    month_b: str = Field(..., pattern=MONTH_RE, description="비교(이후) 달")


def compare_months(uid: str, a: CompareArgs) -> tuple[dict, str]:
    phase_b, elapsed_b, _ = _projection(a.month_b)
    same_period = phase_b == "current"
    full_a = _rows(uid, *_month_bounds(a.month_a))
    # 진행 중인 달은 끝나지 않았으므로, 기준 달도 같은 날짜까지만 잘라 공정하게 비교한다
    ra = _rows(uid, *_first_days_bounds(a.month_a, elapsed_b)) if same_period else full_a
    rb = _rows(uid, *_month_bounds(a.month_b))
    ca, cb = _cat_totals(ra), _cat_totals(rb)
    ta, tb = sum(ca.values()), sum(cb.values())
    diffs = []
    for c in set(ca) | set(cb):
        va, vb = ca.get(c, 0), cb.get(c, 0)
        diffs.append({"category": c, "month_a": va, "month_b": vb, "diff": vb - va, "change_pct": _pct(vb, va)})
    diffs.sort(key=lambda x: abs(x["diff"]), reverse=True)
    result = {
        "basis": (f"{a.month_b}는 진행 중이라 두 달 모두 1~{elapsed_b}일 기준으로 비교" if same_period else "두 달 전체 비교"),
        "month_a": {"month": a.month_a, "total": ta, "count": len(ra),
                    "full_month_total": sum(r["amount"] for r in full_a) if same_period else None},
        "month_b": {"month": a.month_b, "total": tb, "count": len(rb)},
        "total_diff": tb - ta, "total_change_pct": _pct(tb, ta),
        "category_changes": diffs,
        "increased": [d["category"] for d in diffs if d["diff"] > 0],
    }
    suffix = f" (1~{elapsed_b}일 기준)" if same_period else ""
    return result, f"{a.month_a} {ta:,}원 → {a.month_b} {tb:,}원{suffix}"


class TrendArgs(BaseModel):
    category: str
    months: Optional[int] = Field(None, ge=2, le=12, description="최근 몇 개월 (기본 6)")

    @field_validator("category")
    @classmethod
    def valid_category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category는 다음 중 하나여야 합니다: {', '.join(CATEGORIES)}")
        return v


def get_category_trend(uid: str, a: TrendArgs) -> tuple[dict, str]:
    n = a.months or 6
    cur = goal_service.current_month()
    months = [goal_service._prev_month(cur, i) for i in range(n - 1, -1, -1)]
    start, _ = _month_bounds(months[0])
    _, end = _month_bounds(cur)
    rows = [r for r in _rows(uid, start, end) if r["category"] == a.category]
    by_m = defaultdict(lambda: [0, 0])
    for r in rows:
        by_m[r["date"][:7]][0] += r["amount"]
        by_m[r["date"][:7]][1] += 1
    series = [{"month": m, "total": by_m[m][0], "count": by_m[m][1]} for m in months]
    full = [s for s in series if s["month"] != cur]
    avg = round(sum(s["total"] for s in full) / len(full)) if full else 0
    result = {"category": a.category, "months": series, "average_excluding_current": avg,
              "current_month_note": f"{cur}는 진행 중인 달"}
    return result, f"{a.category} 최근 {n}개월 추이 (월평균 {avg:,}원)"


class OverspendArgs(BaseModel):
    month: str = Field(..., pattern=MONTH_RE)


def detect_overspending(uid: str, a: OverspendArgs) -> tuple[dict, str]:
    """규칙(코드): 이번 달 값이 직전 3개월 평균의 130% 이상이고 2만 원 이상 많으면 과소비.
    진행 중인 달은 경과 7일 이상이면 월말 예상치로, 그 전에는 실제 사용액으로 비교한다."""
    phase, elapsed, days = _projection(a.month)
    rows = _rows(uid, *_month_bounds(a.month))
    cur_cat = _cat_totals(rows)
    cur_cnt = defaultdict(int)
    for r in rows:
        cur_cnt[r["category"]] += 1
    basis = [goal_service._prev_month(a.month, i) for i in (1, 2, 3)]
    base_rows = _rows(uid, _month_bounds(basis[-1])[0], _month_bounds(basis[0])[1])
    have = sorted({r["date"][:7] for r in base_rows})
    if not have:
        return {"month": a.month, "available": False, "reason": "비교할 이전 3개월 데이터가 없습니다."}, "비교 데이터 없음"
    n = len(have)
    base_cat = {c: v / n for c, v in _cat_totals(base_rows).items()}
    base_cnt = defaultdict(int)
    for r in base_rows:
        base_cnt[r["category"]] += 1
    use_projection = phase == "current" and elapsed >= 7
    flagged = []
    for c, v in cur_cat.items():
        value = round(v / elapsed * days) if use_projection else v
        avg = base_cat.get(c, 0)
        if value >= avg * 1.3 and value - avg >= 20000:
            flagged.append({
                "category": c, "this_month_spent": v,
                "compared_value": value, "compared_as": "월말 예상" if use_projection else "실제 사용액",
                "average_3m": round(avg), "increase_pct": _pct(value, avg),
                "count_this_month": cur_cnt[c], "count_average_3m": round(base_cnt[c] / n, 1),
            })
    flagged.sort(key=lambda x: x["compared_value"] - x["average_3m"], reverse=True)
    goal, _ = goal_service.get_goal(uid, a.month)
    goal_alerts = []
    if goal:
        p = goal_service.progress(uid, a.month, goal)
        if p["total"] and p["total"]["status"] != "good":
            goal_alerts.append({"target": "총예산", **{k: p["total"][k] for k in ("budget", "spent", "projected", "status")}})
        for c in p["categories"]:
            if c["status"] != "good":
                goal_alerts.append({"target": c["category"], "budget": c["limit"], "spent": c["spent"],
                                    "projected": c["projected"], "status": c["status"]})
    result = {
        "month": a.month, "available": True, "basis_months": have,
        "rule": "직전 3개월 평균 대비 130% 이상 & 2만 원 이상 증가",
        "early_month": phase == "current" and elapsed < 7,
        "flagged": flagged, "goal_alerts": goal_alerts,
    }
    names = ", ".join(f"{f['category']} {f['increase_pct']:+}%" for f in flagged[:3]) or "없음"
    return result, f"{a.month} 과소비 탐지: {names}"


class GoalArgs(BaseModel):
    month: str = Field(..., pattern=MONTH_RE)


def get_goal_progress(uid: str, a: GoalArgs) -> tuple[dict, str]:
    goal, inherited = goal_service.get_goal(uid, a.month)
    if not goal:
        # 목표가 없어도 '지금까지 얼마, 월말 예상 얼마'는 답할 수 있어야 한다 (설명과 실제 결과를 맞춤)
        spent, _ = goal_service.spent_so_far(uid, a.month)
        phase, elapsed, days = _projection(a.month)
        projected = round(spent / elapsed * days) if phase == "current" and elapsed >= 3 else None
        return {"month": a.month, "has_goal": False, "spent_so_far": spent,
                "elapsed_days": elapsed, "days_in_month": days, "projected_month_end": projected,
                "suggestion": goal_service.suggest(uid, a.month)}, \
            f"{a.month} 목표 없음 · 현재 {spent:,}원" + (f", 월말 예상 {projected:,}원" if projected else "")
    p = goal_service.progress(uid, a.month, goal)
    result = {"month": a.month, "has_goal": True, "inherited_from": inherited,
              "total_budget": goal["total_budget"], "category_limits": goal.get("category_limits", []),
              "progress": p}
    t = p["total"]
    return result, f"{a.month} 목표 {t['budget']:,}원 중 {t['spent']:,}원 사용({t['used_pct']}%)"


class LimitArg(BaseModel):
    category: str
    limit: int = Field(..., gt=0)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category는 다음 중 하나여야 합니다: {', '.join(CATEGORIES)}")
        return v


class ProposeArgs(BaseModel):
    month: str = Field(..., pattern=MONTH_RE)
    total_budget: int = Field(..., gt=0, le=100_000_000)
    category_limits: list[LimitArg] = Field(default_factory=list, max_length=3)
    reason: str = Field(..., max_length=300)


def propose_goal(uid: str, a: ProposeArgs) -> tuple[dict, str]:
    """저장하지 않는다. 검증만 하고 '제안'을 돌려주며, 화면에 [적용] 버튼이 뜬다."""
    if a.month < goal_service.current_month():
        raise ValueError("지난 달 목표는 바꿀 수 없습니다.")
    cats = [c.category for c in a.category_limits]
    if len(cats) != len(set(cats)):
        raise ValueError("같은 카테고리를 두 번 넣을 수 없습니다.")
    if any(c.limit > a.total_budget for c in a.category_limits):
        raise ValueError("카테고리 한도는 총예산보다 클 수 없습니다.")
    if a.month == goal_service.current_month():
        spent_total, spent_cat = goal_service.spent_so_far(uid, a.month)
        if a.total_budget < spent_total:
            raise ValueError(f"총예산 {a.total_budget:,}원이 이번 달에 이미 쓴 {spent_total:,}원보다 작습니다. 이미 쓴 금액보다 크게 잡으세요.")
        low = [f"{c.category}(한도 {c.limit:,}원 < 이미 {spent_cat[c.category]:,}원 사용)"
               for c in a.category_limits if c.limit < spent_cat.get(c.category, 0)]
        if low:
            raise ValueError("이번 달에 이미 쓴 금액보다 작은 한도가 있습니다: " + ", ".join(low)
                             + ". 남은 기간을 고려해 이미 쓴 금액보다 크게 잡으세요.")
    current, _ = goal_service.get_goal(uid, a.month)
    proposal = {"month": a.month, "total_budget": a.total_budget,
                "category_limits": [c.model_dump() for c in a.category_limits], "reason": a.reason}
    result = {"saved": False, "note": "제안만 만들어졌습니다. 사용자가 화면의 [적용] 버튼을 눌러야 저장됩니다.",
              "proposal": proposal,
              "current_goal": None if not current else {"total_budget": current["total_budget"],
                                                        "category_limits": current.get("category_limits", [])}}
    return result, f"{a.month} 목표 제안: 총 {a.total_budget:,}원"


# ---------------------------------------------------------------- 레지스트리 + OpenAI 스키마
_month = {"type": "string", "description": "YYYY-MM"}
_date = {"type": "string", "description": "YYYY-MM-DD"}
_cat_enum = {"type": "string", "enum": list(CATEGORIES)}

REGISTRY: dict[str, tuple[type[BaseModel], Callable, str, dict]] = {
    "search_transactions": (SearchArgs, search_transactions, "거래 검색", {
        "description": "기간 안의 거래를 가맹점 이름(부분 일치)·카테고리·최소 금액으로 찾아 건수, 합계, 가맹점별 집계, 최근 항목을 돌려준다. "
                       "특정 가게에 몇 번/얼마 썼는지, 큰 지출이 뭐였는지 같은 질문에 쓴다.",
        "properties": {"start_date": _date, "end_date": _date,
                       "merchant_query": {"type": ["string", "null"], "description": "가맹점 이름 일부. 없으면 null"},
                       "category": {**_cat_enum, "type": ["string", "null"], "enum": list(CATEGORIES) + [None]},
                       "min_amount": {"type": ["integer", "null"]},
                       "limit": {"type": ["integer", "null"], "description": "돌려받을 최근 항목 수(1~20). 기본 10"}},
    }),
    "get_monthly_summary": (MonthArgs, get_monthly_summary, "월 요약", {
        "description": "한 달의 총지출, 건수, 카테고리별 금액과 비중, 상위 가맹점, 지난달 대비 변화를 돌려준다. 진행 중인 달이면 월말 예상치도 준다.",
        "properties": {"month": _month},
    }),
    "compare_months": (CompareArgs, compare_months, "두 달 비교", {
        "description": "두 달의 총지출과 카테고리별 증감(금액·%)을 비교한다. 뒤의 달이 진행 중이면 두 달 모두 같은 날짜까지만 비교한다. 결과의 increased에 늘어난 카테고리 목록이 있다. '지난달보다 뭐가 늘었어?' 같은 질문에 쓴다.",
        "properties": {"month_a": {**_month, "description": "기준(이전) 달 YYYY-MM"},
                       "month_b": {**_month, "description": "비교(이후) 달 YYYY-MM"}},
    }),
    "get_category_trend": (TrendArgs, get_category_trend, "카테고리 추이", {
        "description": "한 카테고리의 최근 N개월(기본 6) 월별 금액·건수와 월평균을 돌려준다.",
        "properties": {"category": _cat_enum, "months": {"type": ["integer", "null"]}},
    }),
    "detect_overspending": (OverspendArgs, detect_overspending, "과소비 탐지", {
        "description": "규칙으로 과소비 카테고리를 찾는다(직전 3개월 평균 대비 130% 이상, 2만 원 이상 증가). 목표가 있으면 초과·초과 예상 항목도 준다. "
                       "'뭐가 문제야', '어디서 줄여야 해' 같은 질문에 쓴다.",
        "properties": {"month": _month},
    }),
    "get_goal_progress": (GoalArgs, get_goal_progress, "목표 진행 상황", {
        "description": "그 달의 절약 목표(총예산·카테고리 한도)와 사용률, 월말 예상, 상태를 돌려준다. 목표가 없으면 지금까지 쓴 금액·월말 예상과 목표 추천값을 준다.",
        "properties": {"month": _month},
    }),
    "propose_goal": (ProposeArgs, propose_goal, "목표 변경 제안", {
        "description": "절약 목표 변경안을 만든다. 저장하지 않으며 사용자가 화면에서 적용 버튼을 눌러야 저장된다. "
                       "사용자가 목표를 정하거나 바꿔 달라고 할 때만 쓴다. 근거 숫자는 다른 도구로 먼저 확인한다.",
        "properties": {"month": _month, "total_budget": {"type": "integer"},
                       "category_limits": {"type": "array", "maxItems": 3, "items": {
                           "type": "object", "additionalProperties": False, "required": ["category", "limit"],
                           "properties": {"category": _cat_enum, "limit": {"type": "integer"}}}},
                       "reason": {"type": "string", "description": "왜 이 값인지 한두 문장"}},
    }),
}


def openai_tools() -> list[dict]:
    tools = []
    for name, (_, _, _, spec) in REGISTRY.items():
        props = spec["properties"]
        tools.append({"type": "function", "function": {
            "name": name, "description": spec["description"], "strict": True,
            "parameters": {"type": "object", "additionalProperties": False,
                           "required": list(props.keys()), "properties": props},
        }})
    return tools


def execute(uid: str, name: str, raw_args: str) -> dict:
    """도구 1회 실행 → {"name","label","args","result","summary","ok"}. 실패도 결과로 돌려 모델이 고칠 수 있게 한다."""
    if name not in REGISTRY:
        return {"name": name, "label": name, "args": {}, "ok": False,
                "result": {"error": f"없는 도구입니다: {name}"}, "summary": "없는 도구"}
    model, fn, label, _ = REGISTRY[name]
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return {"name": name, "label": label, "args": {}, "ok": False,
                "result": {"error": "인자가 JSON이 아닙니다."}, "summary": "인자 오류"}
    clean = {k: v for k, v in args.items() if v is not None}
    try:
        parsed = model(**clean)
        result, summary = fn(uid, parsed)
        return {"name": name, "label": label, "args": clean, "ok": True, "result": result, "summary": summary}
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return {"name": name, "label": label, "args": clean, "ok": False,
                "result": {"error": f"인자 검증 실패 — {msg}"}, "summary": "인자 오류"}
    except ValueError as e:
        return {"name": name, "label": label, "args": clean, "ok": False,
                "result": {"error": str(e)}, "summary": str(e)}
