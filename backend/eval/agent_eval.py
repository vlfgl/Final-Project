"""AI Agent 평가 스크립트 — 실제 GPT로 실행 (비용: 전체 1회 약 100원 내외).

무엇을 재나
1. 도구 선택: 질문마다 모델이 '맞는 도구'를 골랐는가 (데이터가 필요 없는 질문엔 도구를 안 썼는가)
2. 정답 일치: 답변에 정답 숫자/이름이 들어 있는가 (정답은 코드로 직접 계산)
3. 숫자 근거율: 답변의 숫자가 이번에 받은 도구 결과(=근거)에 실제로 있는가 → 지어낸 숫자 탐지(휴리스틱)
같은 질문을 baseline(요약을 프롬프트에 넣는 이전 방식)에도 던져 정답 일치를 비교한다.

실행 (backend 폴더, .env에 OPENAI_API_KEY 필요):
    python -m eval.agent_eval            # agent + baseline
    python -m eval.agent_eval --agent-only
결과: 콘솔 표 + eval/results/agent_eval_<시각>.md, .json
데이터: 메모리 DB에 체험용 샘플(6개월, 605건)을 넣어 사용 — 실제 Firestore는 건드리지 않는다.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ["DB_BACKEND"] = "memory"  # .env보다 먼저: 실제 DB를 쓰지 않음
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import CurrentUser  # noqa: E402
from app.services import agent_tools as T  # noqa: E402
from app.services import chat_service, user_service  # noqa: E402
from app.services.summary_service import today_kst  # noqa: E402

UID = "eval-demo"


def tool(name, **args):
    return T.execute(UID, name, json.dumps(args, ensure_ascii=False))["result"]


def build_cases():
    t = today_kst()
    cur = t.strftime("%Y-%m")
    prev = (t.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    prev2 = (t.replace(day=1) - timedelta(days=35)).strftime("%Y-%m")
    p2_label = f"{int(prev2[5:])}월"
    ps, pe = prev + "-01", (t.replace(day=1) - timedelta(days=1)).isoformat()
    three_ago = (t.replace(day=1) - timedelta(days=80)).replace(day=1).isoformat()

    cafe = tool("search_transactions", start_date=cur + "-01", end_date=t.isoformat(), category="카페·간식")
    prev_sum = tool("get_monthly_summary", month=prev)
    p2_sum = tool("get_monthly_summary", month=prev2)
    cmp_ = tool("compare_months", month_a=prev, month_b=cur)
    up = [c for c in cmp_["category_changes"] if c["diff"] > 0]
    over = tool("detect_overspending", month=cur)
    trend = tool("get_category_trend", category="배달", months=6)
    sbux = tool("search_transactions", start_date=ps, end_date=pe, merchant_query="스타벅스")
    big = tool("search_transactions", start_date=three_ago, end_date=t.isoformat(), min_amount=100000)
    taxi = tool("search_transactions", start_date=ps, end_date=pe, merchant_query="카카오T")
    cur_sum = tool("get_monthly_summary", month=cur)

    return [
        {"id": "Q01", "q": "이번 달에 카페 몇 번 갔어?", "expect": ["search_transactions"], "truth": [("count", cafe["count"])]},
        {"id": "Q02", "q": "지난달 총 지출 얼마야?", "expect": ["get_monthly_summary"], "truth": [("won", prev_sum["total"])]},
        {"id": "Q03", "q": f"{p2_label}에 뭐에 제일 많이 썼어?", "expect": ["get_monthly_summary"],
         "truth": [("text", p2_sum["categories"][0]["category"]), ("won", p2_sum["categories"][0]["total"])]},
        {"id": "Q04", "q": "지난달보다 이번 달에 뭐가 늘었어?", "expect_any": [["compare_months"], ["get_monthly_summary"]],
         "truth": [("text", up[0]["category"])] if up else []},
        {"id": "Q05", "q": "요즘 어디서 돈이 새고 있어?", "expect": ["detect_overspending"],
         "truth": [("text", over["flagged"][0]["category"])] if over.get("flagged") else []},
        {"id": "Q06", "q": "최근 6개월 배달비 추이 알려줘", "expect": ["get_category_trend"],
         "truth": [("won", trend["average_excluding_current"])]},
        {"id": "Q07", "q": "지난달 스타벅스에 얼마 썼어?", "expect": ["search_transactions"], "truth": [("won", sbux["total"])]},
        {"id": "Q08", "q": "최근 3개월 동안 10만원 넘게 쓴 거래 뭐 있었어?", "expect": ["search_transactions"],
         "truth": [("count", big["count"])]},
        {"id": "Q09", "q": "지난달 택시 몇 번 탔어?", "expect_any": [["search_transactions"]], "truth": [("count", taxi["count"])]},
        {"id": "Q10", "q": "이번 달 월말까지 얼마 쓸 것 같아?", "expect_any": [["get_monthly_summary"], ["get_goal_progress"]],
         "truth": [("won", cur_sum["projected_month_end"])] if cur_sum.get("projected_month_end") else []},
        {"id": "Q11", "q": "이번 달 목표 지킬 수 있을까?", "expect": ["get_goal_progress"], "truth": []},
        {"id": "Q12", "q": "배달을 줄이고 싶어. 이번 달 목표를 만들어줘", "expect": ["propose_goal"], "truth": [], "expect_action": True},
        {"id": "Q13", "q": "지난달보다 많이 늘어난 카테고리가 있으면 그 카테고리의 최근 6개월 추이도 보여줘",
         "expect": ["get_category_trend"], "expect_any": [["compare_months"], ["detect_overspending"], ["get_monthly_summary"]],
         "truth": [], "multi_step": True},
        {"id": "Q14", "q": "돈 아끼는 일반적인 팁 3가지만 알려줘", "expect_none": True, "truth": []},
        {"id": "Q15", "q": "안녕! 넌 뭘 도와줄 수 있어?", "expect_none": True, "truth": []},
    ]


# ---------------------------------------------------------------- 채점
def variants(kind, v):
    if v is None:
        return []
    if kind == "text":
        return [v]
    if kind == "count":  # 작은 수는 다른 숫자에 우연히 섞이므로 단위까지 붙은 형태만 인정
        return [f"{v}건", f"{v}번", f"{v}회", f"{v} 건", f"{v} 번", f"{v} 회"]
    out = {f"{v:,}", str(v)}
    if kind == "won" and v >= 10000:
        man = v / 10000
        out |= {f"{man:.1f}".rstrip("0").rstrip(".") + "만", f"{round(man)}만", f"{man:,.0f}만"}
    return list(out)


def truth_hit(answer, truth):
    if not truth:
        return None
    a = answer.replace(" ", "")
    return all(any(x.replace(" ", "") in a for x in variants(k, v)) for k, v in truth)


NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers_in(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(float(obj))
    elif isinstance(obj, str):
        for m in NUM.findall(obj):
            acc.add(float(m.replace(",", "")))
    return acc


def ungrounded(answer, evidence_text):
    """답변의 '의미 있는' 숫자(100 이상이거나 % 붙은 것)가 근거에 있는지. 만 원 단위·반올림 허용 (휴리스틱)."""
    try:
        ev = numbers_in(json.loads(evidence_text), set())
    except Exception:
        ev = numbers_in(evidence_text, set())
    bad = []
    for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*만)?(\s*%)?", answer):
        raw, man, pct = m.group(1), m.group(2), m.group(3)
        v = float(raw.replace(",", ""))
        if man:
            v *= 10000
        if not pct and v < 100:
            continue  # 날짜·건수·순위 같은 작은 수는 판단에서 뺀다
        # '-46.7%'를 '46.7% 감소'처럼 부호 없이 쓰는 경우가 많아 절댓값으로 비교한다
        ok = any(abs(v - abs(e)) <= max(1, abs(e) * (0.01 if not man else 0.05)) for e in ev)
        if not ok:
            bad.append(m.group(0).strip())
    return bad


def judge_tools(case, called):
    called_set = set(called)
    if case.get("expect_none"):
        return len(called) == 0
    ok = all(t in called_set for t in case.get("expect", []))
    if case.get("expect_any"):
        ok = ok and any(all(t in called_set for t in group) for group in case["expect_any"])
    return ok


# ---------------------------------------------------------------- 실행
def run_one(mode, q):
    msgs = [{"role": "system", "content": chat_service.agent_system_prompt(UID) if mode == "agent" else ""},
            {"role": "user", "content": q}]
    t0 = time.time()
    out = chat_service.run_agent(UID, msgs) if mode == "agent" else chat_service.run_baseline(UID, msgs)
    dt = time.time() - t0
    evidence = json.dumps([json.loads(m["content"]) for m in msgs if m["role"] == "tool"], ensure_ascii=False) \
        if mode == "agent" else msgs[0]["content"]
    return out, evidence, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-only", action="store_true")
    args = ap.parse_args()

    u = CurrentUser(UID, None, None, True)
    user_service.give_consent(u)
    user_service.seed_demo_data(u)
    cases = build_cases()
    modes = ["agent"] if args.agent_only else ["agent", "baseline"]
    rows, raw = [], []
    for case in cases:
        rec = {"id": case["id"], "q": case["q"]}
        for mode in modes:
            try:
                out, evidence, dt = run_one(mode, case["q"])
            except Exception as e:
                print(f"{case['id']} {mode}: 실패 {type(e).__name__}: {e}")
                rec[mode] = {"error": str(e)}
                continue
            called = [t["tool"] for t in out["trace"] if t["ok"]]
            r = {"answer": out["reply"], "tools": called, "steps": max([t["step"] for t in out["trace"]] or [0]),
                 "model_calls": out["usage"].get("model_calls"), "seconds": round(dt, 1),
                 "truth_hit": truth_hit(out["reply"], case["truth"]),
                 "ungrounded": ungrounded(out["reply"], evidence),
                 "actions": out["actions"]}
            if mode == "agent":
                r["tool_ok"] = judge_tools(case, called) and (not case.get("expect_action") or bool(out["actions"]))
                r["multi_step_ok"] = (r["steps"] >= 2) if case.get("multi_step") else None
            rec[mode] = r
            print(f"{case['id']} {mode:8} tools={called} truth={r['truth_hit']} ungrounded={r['ungrounded']} ({r['seconds']}s)")
        raw.append(rec)
        rows.append(rec)

    # 요약 지표
    def rate(vals):
        vals = [v for v in vals if v is not None]
        return (sum(1 for v in vals if v), len(vals))
    ag = [r["agent"] for r in rows if "error" not in r.get("agent", {"error": 1})]
    tool_ok = rate([r["tool_ok"] for r in ag])
    truth_ag = rate([r["truth_hit"] for r in ag])
    grounded_ag = rate([not r["ungrounded"] for r in ag])
    lines = ["# AI Agent 평가 결과", "", f"- 실행: {datetime.now():%Y-%m-%d %H:%M} · 모델 `{chat_service.settings.OPENAI_MODEL}` · 질문 {len(cases)}개",
             f"- 도구 선택 정확도(agent): **{tool_ok[0]}/{tool_ok[1]}**",
             f"- 정답 일치(agent): **{truth_ag[0]}/{truth_ag[1]}**",
             f"- 숫자 근거율(agent, 지어낸 숫자 없는 답변): **{grounded_ag[0]}/{grounded_ag[1]}**"]
    if "baseline" in modes:
        bl = [r["baseline"] for r in rows if "error" not in r.get("baseline", {"error": 1})]
        truth_bl = rate([r["truth_hit"] for r in bl])
        grounded_bl = rate([not r["ungrounded"] for r in bl])
        lines += [f"- 정답 일치(baseline): **{truth_bl[0]}/{truth_bl[1]}**",
                  f"- 숫자 근거율(baseline, 근거=프롬프트 요약): **{grounded_bl[0]}/{grounded_bl[1]}**"]
    lines += ["", "| ID | 질문 | agent 도구 | 도구 OK | 정답(agent) | 정답(baseline) | 근거 없는 숫자(agent) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    mark = lambda v: "-" if v is None else ("✅" if v else "❌")  # noqa: E731
    for r in rows:
        a, b = r.get("agent", {}), r.get("baseline", {})
        lines.append(f"| {r['id']} | {r['q']} | {', '.join(a.get('tools', [])) or '(없음)'} | {mark(a.get('tool_ok'))} | "
                     f"{mark(a.get('truth_hit'))} | {mark(b.get('truth_hit')) if b else '-'} | {', '.join(a.get('ungrounded', [])) or '없음'} |")
    lines += ["", "> 숫자 근거율은 휴리스틱이다: 답변의 100 이상 숫자·%가 근거 데이터에 (반올림·만 원 단위 허용) 있는지 본다. "
              "모델이 근거 숫자로 직접 계산한 값(예: 차액)은 ❌로 잡힐 수 있으니 표의 숫자를 직접 확인한다."]
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    (out_dir / f"agent_eval_{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / f"agent_eval_{stamp}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(lines[:9]))
    print(f"\n저장: eval/results/agent_eval_{stamp}.md")


if __name__ == "__main__":
    main()
