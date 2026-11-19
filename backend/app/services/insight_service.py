"""소비 알림 카드 — AI를 쓰지 않는다(비용 0, 숫자는 코드 계산).

접속할 때마다 GPT를 부르면 질문하지 않아도 비용이 나가고 서버가 느릴 때 화면이 늦게 뜬다.
그래서 카드 내용은 과소비 탐지 규칙(agent_tools.detect_overspending)과 목표 진행률로 만들고,
AI(Agent)는 사용자가 카드의 버튼을 눌렀을 때만 부른다.
"""
from app.services import agent_tools, goal_service

MAX_CARDS = 2


def _won(n: int) -> str:
    return f"{n:,}원"


def _j(word: str, with_batchim: str, without: str) -> str:
    """받침에 맞는 조사: _j('배달', '을', '를') → '배달을', _j('식비', '을', '를') → '식비를'"""
    ch = word[-1]
    has = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    return word + (with_batchim if has else without)


def build(uid: str) -> dict:
    month = goal_service.current_month()
    res, _ = agent_tools.detect_overspending(uid, agent_tools.OverspendArgs(month=month))
    cards: list[dict] = []
    if not res.get("available"):
        return {"month": month, "cards": [], "reason": res.get("reason")}

    # 1) 목표 초과·초과 예상 (사용자가 직접 정한 기준이라 먼저 보여준다)
    for g in sorted(res["goal_alerts"], key=lambda x: x["status"] != "over"):
        name = g["target"]
        is_total = name == "총예산"
        label = "이번 달 총예산" if is_total else f"{name} 한도"
        if g["status"] == "over":
            title = f"{_j(label, '을', '를')} 넘었어요"
            detail = f"{label} {_won(g['budget'])} 중 {_won(g['spent'])}을 썼어요({_won(g['spent'] - g['budget'])} 초과)."
        else:
            title = f"이 페이스면 {_j(label, '을', '를')} 넘어요"
            detail = f"지금까지 {_won(g['spent'])}, 이대로면 월말 {_won(g['projected'])}으로 {label} {_won(g['budget'])}보다 많아요."
        topic = "전체 지출" if is_total else name
        cards.append({
            "kind": "goal_alert", "level": "danger" if g["status"] == "over" else "warning",
            "key": f"goal:{name}", "title": title, "detail": detail,
            "actions": [{"label": "자세히 분석하기",
                         "prompt": f"이번 달 {_j(topic, '이', '가')} 목표를 {'넘었어' if g['status'] == 'over' else '넘을 것 같아'}. 원인과 남은 기간 실천 방법을 알려줘"}],
        })

    # 2) 평소보다 크게 늘어난 카테고리 (직전 3개월 평균 대비 130% 이상 & 2만 원 이상)
    goal_targets = {g["target"] for g in res["goal_alerts"]}
    for f in res["flagged"]:
        if f["category"] in goal_targets:
            continue  # 같은 카테고리를 두 번 알리지 않는다
        c = f["category"]
        basis = "월말 예상" if f["compared_as"] == "월말 예상" else "지금까지"
        cmp_txt = f"{basis} {_won(f['compared_value'])}" if f["compared_as"] == "월말 예상" else _won(f["this_month_spent"])
        cards.append({
            "kind": "overspending", "level": "warning", "key": f"over:{c}",
            "title": f"이번 달 {c} 지출이 평소보다 많아요",
            "detail": (f"이번 달 {c}에 {_won(f['this_month_spent'])}을 썼어요"
                       + (f"({cmp_txt})" if f["compared_as"] == "월말 예상" else "")
                       + f". 최근 3개월 평균 {_won(f['average_3m'])}보다 {f['increase_pct']}% 많아요."),
            "actions": [
                {"label": "자세히 분석하기", "prompt": f"이번 달 {c} 지출이 왜 늘었는지 분석해줘"},
                {"label": "목표로 관리하기", "prompt": f"{_j(c, '을', '를')} 줄이고 싶어. 이번 달 목표를 만들어줘"},
            ],
        })
    return {"month": month, "early_month": res["early_month"], "rule": res["rule"], "cards": cards[:MAX_CARDS]}
