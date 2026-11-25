"""인증·사용자 분리 포함 API 테스트 (DB_BACKEND=memory, 가짜 토큰 'dev:<uid>')."""
import os, sys
os.environ["DB_BACKEND"] = "memory"; os.environ["OPENAI_API_KEY"] = "test"; os.environ["DAILY_CHAT_LIMIT"] = "3"; os.environ["DAILY_IMAGE_LIMIT"] = "3"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from app.services import chat_service

c = TestClient(app)
H = lambda uid: {"Authorization": f"Bearer dev:{uid}"}
ANON = {"Authorization": "Bearer dev:guest1:anon"}

def fake_client():
    m = MagicMock()
    m.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="테스트 답변", tool_calls=None))]
    return m

# 1) 인증 없으면 401
assert c.get("/api/transactions").status_code == 401
assert c.get("/api/me").status_code == 401
assert c.get("/api/transactions", headers={"Authorization": "Bearer garbage"}).status_code == 401

# 2) 로그인했지만 동의 전 → 403 consent_required
me = c.get("/api/me", headers=H("alice")).json()
assert me["consented"] is False and me["email"] == "alice@test.dev", me
r = c.get("/api/transactions", headers=H("alice")); assert r.status_code == 403 and r.json()["detail"] == "consent_required"

# 3) 동의 후 사용 가능
assert c.post("/api/me/consent", headers=H("alice")).json()["consented"] is True
assert c.get("/api/transactions", headers=H("alice")).json() == []
r = c.post("/api/transactions", headers=H("alice"), json={"date": "2026-11-01", "amount": 12000, "merchant": "김밥천국", "category": "식비"}); assert r.status_code == 201
alice_item = r.json()

# 4) 사용자 분리: bob은 alice 데이터를 못 보고, 수정·삭제도 못 함
c.post("/api/me/consent", headers=H("bob"))
assert c.get("/api/transactions", headers=H("bob")).json() == []
assert c.get("/api/transactions/summary", headers=H("bob")).json()["count"] == 0
assert c.put(f"/api/transactions/{alice_item['id']}", headers=H("bob"), json={"amount": 1}).status_code == 404
assert c.delete(f"/api/transactions/{alice_item['id']}", headers=H("bob")).status_code == 404
assert c.get("/api/transactions/summary", headers=H("alice")).json()["count"] == 1

# 5) 채팅: 사용자별 저장 + 하루 한도(테스트 3회)
with patch.object(chat_service, "_get_client", side_effect=fake_client):
    r = c.post("/api/chat", headers=H("alice"), json={"message": "이번 달 어때?"}); assert r.status_code == 200, r.text
    assert r.json()["remaining_today"] == 2
    cid = r.json()["conversation_id"]
    assert c.get("/api/conversations", headers=H("bob")).json() == []
    assert c.get(f"/api/conversations/{cid}", headers=H("bob")).status_code == 404
    assert c.post("/api/chat", headers=H("bob"), json={"message": "x", "conversation_id": cid}).status_code == 404
    c.post("/api/chat", headers=H("alice"), json={"message": "2"}); c.post("/api/chat", headers=H("alice"), json={"message": "3"})
    r = c.post("/api/chat", headers=H("alice"), json={"message": "4"}); assert r.status_code == 429, r.text
    assert len(c.get("/api/conversations", headers=H("alice")).json()) == 3

# 6) 체험(익명) 계정: 동의 → 샘플 데이터 605건, 두 번 호출해도 중복 없음, 일반 계정은 불가
c.post("/api/me/consent", headers=ANON)
assert c.get("/api/me", headers=ANON).json()["is_anonymous"] is True
assert c.post("/api/me/demo", headers=ANON).json()["seeded"] == 605
assert c.post("/api/me/demo", headers=ANON).json()["seeded"] == 0
assert c.get("/api/transactions/summary", headers=ANON).json()["count"] == 605
assert c.post("/api/me/demo", headers=H("alice")).status_code == 400

# 7) 내 데이터 전체 삭제 → 다시 동의 필요, 데이터 0건, 다른 사용자 영향 없음
d = c.delete("/api/me", headers=H("alice")).json(); assert d["deleted"]["transactions"] == 1 and d["deleted"]["conversations"] == 3, d
assert c.get("/api/transactions", headers=H("alice")).status_code == 403
c.post("/api/me/consent", headers=H("alice"))
assert c.get("/api/transactions", headers=H("alice")).json() == []
assert c.get("/api/transactions/summary", headers=ANON).json()["count"] == 605

# 8) 기존 검증 유지
assert c.post("/api/transactions", headers=H("bob"), json={"date": "2026-13-01", "amount": 1, "merchant": "x", "category": "식비"}).status_code == 422
assert c.get("/docs").status_code == 200 and c.get("/health").json() == {"status": "ok"}
r = c.options("/api/transactions", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
assert r.status_code == 200 and "authorization" in r.headers.get("access-control-allow-headers", "").lower()
# 9) 새 데이터 모델: 필드, 카테고리 고정 목록, 부분 수정 시 category_by, 검증
H2 = H("carol"); c.post("/api/me/consent", headers=H2)
r = c.post("/api/transactions", headers=H2, json={"date": "2026-10-28", "amount": 5600, "merchant": "  스타벅스 강남역점 ", "category": "카페·간식"})
t = r.json(); assert r.status_code == 201 and t["merchant"] == "스타벅스 강남역점" and t["source"] == "manual" and t["created_at"], t
bad = [
    {"date": "2026-10-28", "amount": 5600, "merchant": "x", "category": "커피"},      # 목록에 없는 카테고리
    {"date": "2026-10-28", "amount": 0, "merchant": "x", "category": "식비"},         # 금액 0
    {"date": "2026-10-28", "amount": 100, "merchant": "   ", "category": "식비"},     # 빈 가맹점
    {"date": "2026-10-28", "amount": 100, "category": "식비"},                         # 가맹점 누락
]
for b in bad:
    assert c.post("/api/transactions", headers=H2, json=b).status_code == 422, b
u = c.put(f"/api/transactions/{t['id']}", headers=H2, json={"category": "식비"}).json()
assert u["category"] == "식비" and u["category_by"] == "user" and u["amount"] == 5600
assert c.put(f"/api/transactions/{t['id']}", headers=H2, json={"category": "없는것"}).status_code == 422
cats = c.get("/api/transactions/categories").json(); assert "배달" in cats and len(cats) == 12
s = c.get("/api/transactions/summary", headers=ANON).json()
assert s["categories"][0]["category"] == "주거·통신" and s["metrics"]["max"]["merchant"], s["metrics"]["max"]
from app.services.summary_service import today_kst
assert s["period"].endswith(today_kst().isoformat()), s["period"]       # 샘플이 오늘로 끝나도록 이동됨
assert s["current_month"]["month"] == today_kst().strftime("%Y-%m") and s["current_month"]["total"] > 0

# 10) 요약 기준일: 이번 달 거래가 없으면 0원, 비교는 과거 달 평균 기준
from app.services.summary_service import build_summary
from datetime import date as _d
rows = [{"date": "2026-09-10", "amount": 100000, "merchant": "a", "category": "식비"},
        {"date": "2026-10-10", "amount": 200000, "merchant": "b", "category": "배달"}]
bs = build_summary(rows, today=_d(2026, 11, 1))
assert bs["current_month"]["month"] == "2026-11" and bs["current_month"]["total"] == 0, bs["current_month"]
assert bs["metrics"]["monthly_average"] == 150000 and bs["current_month"]["vs_monthly_average_pct"] is None  # 월초
bs = build_summary(rows + [{"date": "2026-11-10", "amount": 60000, "merchant": "c", "category": "식비"}], today=_d(2026, 11, 15))
assert bs["current_month"]["projected_total"] == 120000 and bs["current_month"]["vs_monthly_average_pct"] == -20.0, bs["current_month"]
# 11) 이전 구조 문서가 섞여 있어도 목록·요약이 깨지지 않음
from app.db import get_store, user_col
get_store().add(user_col("carol", "transactions"), {"date": "2026-10-01", "value": 999, "memo": "식비 | old"})
assert c.get("/api/transactions", headers=H2).status_code == 200
assert c.get("/api/transactions/summary", headers=H2).status_code == 200
# 12) 이미지 인식: 후처리(연도 보정·취소·중복·규칙), 일괄 저장, 한도
import json
from app.services import vision_service
from app.services.summary_service import today_kst as _today
td = _today()
future = td.replace(day=1) + __import__("datetime").timedelta(days=40)   # 다음 달 → 연도 없는 캡처 오추정 상황
ymd = lambda d: {"year": None, "month": d.month, "day": d.day, "weekday": None}          # 캡처에 연도가 없는 경우
FAKE = {"image_type": "card_statement", "transactions": [
    {**ymd(td), "amount": 23500, "merchant": "배달의민족", "category": "배달", "status": "spent", "confidence": "high"},
    {**ymd(td), "amount": 4500, "merchant": "메가MGC커피 역삼점", "category": "카페·간식", "status": "spent", "confidence": "low"},
    {**ymd(td), "amount": 12000, "merchant": "GS25", "category": "장보기·생활", "status": "canceled", "confidence": "high"},
    {**ymd(future), "amount": 8000, "merchant": "김밥천국", "category": "식비", "status": "spent", "confidence": "high"},
    {"year": None, "month": None, "day": 5, "weekday": None, "amount": 3000, "merchant": "CU", "category": "장보기·생활", "status": "spent", "confidence": "high"},
    {**ymd(td), "amount": 0, "merchant": "합계", "category": "기타", "status": "spent", "confidence": "high"},
    {**ymd(td), "amount": 9900, "merchant": "카카오T 택시", "category": "기타", "status": "spent", "confidence": "high"},
    {**ymd(td), "amount": 50000, "merchant": "박채원", "category": "기타", "status": "income", "confidence": "high"},
    {**ymd(td), "amount": 10000, "merchant": "빼따구", "category": "식비", "status": "spent", "confidence": "high"},
]}
def fake_vision(**kw):
    assert kw["response_format"]["type"] == "json_schema" and kw["messages"][0]["content"][1]["type"] == "image_url"
    m = MagicMock(); m.choices = [MagicMock(message=MagicMock(content=json.dumps(FAKE)))]; return m
vc = MagicMock(); vc.chat.completions.create.side_effect = fake_vision
HD = H("dave"); c.post("/api/me/consent", headers=HD)
# 기존 거래(중복 대상) + 사용자가 직접 고친 분류(규칙: 카카오T 택시 → 교통)
c.post("/api/transactions", headers=HD, json={"date": td.isoformat(), "amount": 23500, "merchant": "배달의 민족", "category": "배달"})
c.post("/api/transactions", headers=HD, json={"date": "2026-01-03", "amount": 7000, "merchant": "카카오T 택시", "category": "교통"})
c.post("/api/transactions", headers=HD, json={"date": td.isoformat(), "amount": 10000, "merchant": "뼈따구", "category": "식비"})  # 오타를 고쳐 저장한 기존 거래
IMG = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="
with patch.object(vision_service, "_get_client", return_value=vc):
    r = c.post("/api/uploads/extract", headers=HD, json={"data_url": IMG}); assert r.status_code == 200, r.text
    ex = r.json(); items = {i["merchant"]: i for i in ex["items"]}
    assert ex["image_type"] == "card_statement" and ex["remaining_today"] == 2
    assert "합계" not in items and len(items) == 8                                   # 0원 행 제외
    assert items["박채원"]["status"] == "income" and not items["박채원"]["include"]        # 입금은 제외
    assert items["빼따구"]["duplicate"] and not items["빼따구"]["include"] and "비슷한" in items["빼따구"]["notes"][-1]
    assert items["배달의민족"]["duplicate"] and not items["배달의민족"]["include"]       # 띄어쓰기 달라도 중복
    assert items["메가MGC커피 역삼점"]["low_confidence"] and items["메가MGC커피 역삼점"]["include"]
    assert items["GS25"]["status"] == "canceled" and not items["GS25"]["include"]
    assert items["김밥천국"]["date"] == future.replace(year=future.year - 1).isoformat()  # 연도 보정
    assert items["CU"]["date"] is None and not items["CU"]["include"]
    assert items["카카오T 택시"]["category"] == "교통" and items["카카오T 택시"]["category_by"] == "rule"
    assert c.post("/api/uploads/extract", headers=HD, json={"data_url": "data:text/html;base64,AAAA"}).status_code == 422
    c.post("/api/uploads/extract", headers=HD, json={"data_url": IMG}); c.post("/api/uploads/extract", headers=HD, json={"data_url": IMG})
    assert c.post("/api/uploads/extract", headers=HD, json={"data_url": IMG}).status_code == 429
vc2 = MagicMock(); vc2.chat.completions.create.side_effect = RuntimeError("down")
with patch.object(vision_service, "_get_client", return_value=vc2):
    assert c.post("/api/uploads/extract", headers=H("erin"), json={"data_url": IMG}).status_code == 403   # 동의 전
    c.post("/api/me/consent", headers=H("erin"))
    assert c.post("/api/uploads/extract", headers=H("erin"), json={"data_url": IMG}).status_code == 502
# 일괄 저장
before = len(c.get("/api/transactions", headers=HD).json())
bulk = {"items": [
    {"date": td.isoformat(), "amount": 4500, "merchant": "메가MGC커피 역삼점", "category": "카페·간식", "source": "screenshot", "category_by": "ai"},
    {"date": td.isoformat(), "amount": 9900, "merchant": "카카오T 택시", "category": "교통", "source": "screenshot", "category_by": "rule"},
    {"date": td.isoformat(), "amount": 18000, "merchant": "본죽", "category": "식비", "source": "receipt", "category_by": "user"},
]}
r = c.post("/api/transactions/bulk", headers=HD, json=bulk); assert r.status_code == 201 and r.json()["created"] == 3, r.text
rows = c.get("/api/transactions", headers=HD).json(); assert len(rows) == before + 3
assert {x["source"] for x in rows if x["merchant"] == "본죽"} == {"receipt"}
assert c.post("/api/transactions/bulk", headers=HD, json={"items": [{**bulk["items"][0], "source": "manual"}]}).status_code == 422
assert c.post("/api/transactions/bulk", headers=HD, json={"items": []}).status_code == 422
# 사용자가 '본죽'을 직접 분류(user)로 저장 → 이후 규칙에 포함
from app.services.upload_service import category_rules
assert category_rules("dave").get("본죽") == "식비"
# 13) 날짜 규칙: 같은 입력이면 항상 같은 날짜
from app.services.upload_service import resolve_date
T = _d(2026, 11, 2)
assert resolve_date(None, 11, 15, T)[0] == "2025-11-15"          # 연도 없음 → 가장 가까운 과거
assert resolve_date(None, 10, 28, T)[0] == "2026-10-28"
assert resolve_date(None, 11, 2, T)[0] == "2026-11-02"           # 오늘
assert resolve_date(2023, 11, 15, T)[0] == "2023-11-15" and "1년 이상" in resolve_date(2023, 11, 15, T)[1][0]
assert resolve_date(2026, 12, 1, T)[1] == ["미래 날짜예요. 확인해 주세요."]
assert resolve_date(None, None, 5, T)[0] is None and resolve_date(None, 2, 30, T)[0] is None
assert resolve_date(None, 2, 29, _d(2026, 3, 1))[0] == "2024-02-29"   # 윤년
# 요일로 월·연도 확정: K-패스 캡처 "15일(목)"만 보이는 경우 (2026-11-02 기준)
assert resolve_date(None, None, 15, T, "목")[0] == "2026-10-15"
assert resolve_date(None, None, 12, T, "월")[0] == "2026-10-12"
assert resolve_date(None, None, 15, T)[0] is None                       # 요일도 없으면 확정 불가
assert resolve_date(None, 11, 15, T, "수")[0] == "2023-11-15"           # 월+요일 → 요일이 맞는 해
assert resolve_date(None, None, 31, T, "월")[0] is None or resolve_date(None, None, 31, T, "월")[0].endswith("-31")
assert resolve_date(2026, 10, 28, T)[0] == "2026-10-28"                 # 상세 화면처럼 연도까지 보이는 경우
# 16) 월별 카테고리 합계 (도넛 + 프롬프트)
s = c.get("/api/transactions/summary", headers=ANON).json()
mc = s["monthly_categories"]; last = sorted(mc)[-2]
assert sum(x["total"] for x in mc[last]) == s["monthly_totals"][last]
assert abs(sum(x["share_pct"] for x in mc[last]) - 100) < 1 and mc[last][0]["total"] >= mc[last][-1]["total"]
from app.services.summary_service import to_prompt_text
txt = to_prompt_text(s); assert f"- {last} 카테고리별 지출: " in txt and "배달" in txt
# 17) 월 절약 목표: 저장·이력·이월·진행률·추천·수정 제한·프롬프트·삭제
from app.services import goal_service
from app.services.summary_service import today_kst as _tk
cur = _tk().strftime("%Y-%m"); prev = goal_service._prev_month(cur); nxt = (_tk().replace(day=28) + __import__("datetime").timedelta(days=5)).strftime("%Y-%m")
HG = ANON  # 샘플 데이터(6개월)가 있는 체험 계정
r = c.get(f"/api/goals/{cur}", headers=HG).json()
assert r["goal"] is None and r["editable"] and r["progress"]["spent"] > 0 and r["progress"]["total"] is None
sg = c.get(f"/api/goals/{cur}/suggestion", headers=HG).json()
assert sg["available"] and len(sg["basis_months"]) == 3 and sg["total_budget"] % 10000 == 0 and len(sg["category_limits"]) == 3
assert all(x["category"] not in goal_service.FIXED_CATEGORIES for x in sg["category_limits"])
assert sg["total_budget"] < sg["total_average"]
body = {"total_budget": 1500000, "category_limits": [{"category": "배달", "limit": 150000}, {"category": "카페·간식", "limit": 80000}]}
r = c.put(f"/api/goals/{cur}", headers=HG, json=body); assert r.status_code == 200, r.text
g = r.json(); assert g["goal"]["total_budget"] == 1500000 and g["goal"]["history"] == []
t = g["progress"]["total"]; assert t["budget"] == 1500000 and t["status"] in ("good", "warning", "over") and t["remaining"] == 1500000 - t["spent"]
assert [x["category"] for x in g["progress"]["categories"]] == ["배달", "카페·간식"]
# 중간 변경 → 이력
r = c.put(f"/api/goals/{cur}", headers=HG, json={**body, "total_budget": 1300000}).json()
assert r["goal"]["total_budget"] == 1300000 and r["goal"]["history"][0]["total_budget"] == 1500000
# 같은 값 저장은 이력 안 늘어남
assert len(c.put(f"/api/goals/{cur}", headers=HG, json={**body, "total_budget": 1300000}).json()["goal"]["history"]) == 1
# 다음 달: 문서가 없으면 이번 달 목표를 이어받음
r = c.get(f"/api/goals/{nxt}", headers=HG).json()
assert r["inherited_from"] == cur and r["goal"]["total_budget"] == 1300000 and r["progress"]["phase"] == "future"
# 지난 달 수정 금지, 지난 달은 확정 실적
assert c.put(f"/api/goals/{prev}", headers=HG, json=body).status_code == 400
p = c.get(f"/api/goals/{prev}", headers=HG).json()["progress"]; assert p["phase"] == "past" and p["projected"] == p["spent"]
# 검증: 같은 카테고리 두 번, 한도>총예산, 4개, 없는 카테고리, 잘못된 월
bad = [{"total_budget": 100000, "category_limits": [{"category": "배달", "limit": 1}, {"category": "배달", "limit": 2}]},
       {"total_budget": 100000, "category_limits": [{"category": "배달", "limit": 200000}]}]
for b_ in bad:
    assert c.put(f"/api/goals/{cur}", headers=HG, json=b_).status_code == 400
assert c.put(f"/api/goals/{cur}", headers=HG, json={"total_budget": 9, "category_limits": [{"category": x, "limit": 1} for x in ["식비", "배달", "쇼핑", "교통"]]}).status_code == 422
assert c.put(f"/api/goals/{cur}", headers=HG, json={"total_budget": 9, "category_limits": [{"category": "커피", "limit": 1}]}).status_code == 422
assert c.get("/api/goals/2026-13", headers=HG).status_code == 422
# 다른 사용자에게 안 보임
assert c.get(f"/api/goals/{cur}", headers=H("bob")).json()["goal"] is None
# 채팅 프롬프트에 목표 반영
from app.services.chat_service import build_system_prompt
from app.services.summary_service import get_summary
uid_anon = "guest1"
pt = goal_service.prompt_text(uid_anon); assert "총예산 1,300,000원" in pt and "배달 한도 150,000원" in pt
assert "[절약 목표]" in build_system_prompt(get_summary(uid_anon), pt)
# 월초 페이스: 진행률 계산 함수 단위 확인
assert goal_service._status(100, 50, None) == "over" and goal_service._status(10, 50, 60) == "warning" and goal_service._status(10, 50, 40) == "good"
# 해제 후 이월 대상 없음, 데이터 삭제 시 목표도 삭제
assert c.delete(f"/api/goals/{cur}", headers=HG).status_code == 204
assert c.get(f"/api/goals/{cur}", headers=HG).json()["goal"] is None
c.put(f"/api/goals/{cur}", headers=HG, json=body)
d = c.delete("/api/me", headers=HG).json(); assert d["deleted"]["goals"] == 1, d
# 18) AI Agent: 모델이 고른 도구를 실행하는 루프, 근거(trace), 제안(actions), 단계 한도, 사용자 범위
import json as _json
from types import SimpleNamespace as NS

class ScriptedLLM:
    """모델 응답을 순서대로 흉내 낸다. 각 항목은 ('tools', [(name, args), ...]) 또는 ('text', '답변')."""
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = NS(completions=NS(create=self.create))
    def create(self, **kw):
        self.calls.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        kind, val = self.script.pop(0) if self.script else ("tools", [("get_monthly_summary", {"month": "2026-10"})])
        if kind == "text":
            msg = NS(content=val, tool_calls=None)
        else:
            msg = NS(content=None, tool_calls=[NS(id=f"call_{len(self.calls)}_{i}", function=NS(name=n, arguments=_json.dumps(a, ensure_ascii=False)))
                                               for i, (n, a) in enumerate(val)])
        return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=100, completion_tokens=20))

G = {"Authorization": "Bearer dev:agentdemo:anon"}
c.post("/api/me/consent", headers=G); c.post("/api/me/demo", headers=G)
c.post("/api/me/consent", headers=H("mallory"))
c.post("/api/transactions", headers=H("mallory"), json={"date": "2026-10-05", "amount": 999999, "merchant": "스타벅스 비밀점", "category": "카페·간식"})
cur = _tk().strftime("%Y-%m")
llm = ScriptedLLM([
    ("tools", [("search_transactions", {"start_date": "2026-10-01", "end_date": "2026-10-31", "merchant_query": "스타벅스", "category": None, "min_amount": None, "limit": None}),
               ("detect_overspending", {"month": cur})]),                      # 한 번에 도구 2개 (모델의 선택)
    ("tools", [("get_category_trend", {"category": "커피", "months": None})]),  # 잘못된 인자 → error 결과
    ("tools", [("get_category_trend", {"category": "카페·간식", "months": 3})]),  # 모델이 고쳐서 다시 호출
    ("text", "10월 스타벅스는 N건이에요."),
])
from app.services import chat_service as _cs
with patch.object(_cs, "_get_client", return_value=llm):
    r = c.post("/api/chat", headers=G, json={"message": "10월에 스타벅스 몇 번 갔어? 요즘 뭐가 문제야?"}); assert r.status_code == 200, r.text
res = r.json()
assert res["mode"] == "agent" and res["reply"].startswith("10월 스타벅스")
tr = res["trace"]; assert [t["tool"] for t in tr] == ["search_transactions", "detect_overspending", "get_category_trend", "get_category_trend"], tr
assert [t["ok"] for t in tr] == [True, True, False, True] and tr[0]["step"] == 1 and tr[3]["step"] == 3
assert res["usage"]["model_calls"] == 4 and res["usage"]["prompt_tokens"] == 400
# 도구 결과가 모델에게 전달됨 + 사용자 범위(mallory의 999,999원 스타벅스는 안 보임)
second = llm.calls[1]["messages"]
tool_msgs = [m for m in second if m["role"] == "tool"]
first_result = _json.loads(tool_msgs[0]["content"])
assert first_result["count"] > 0 and all(i["amount"] != 999999 for i in first_result["recent_items"])
assert second[-3]["role"] == "assistant" and len(second[-3]["tool_calls"]) == 2
assert "error" in _json.loads(llm.calls[2]["messages"][-1]["content"])      # 잘못된 인자는 error로 전달
assert llm.calls[0]["tool_choice"] == "auto" and len(llm.calls[0]["tools"]) == 7
assert "오늘" in llm.calls[0]["messages"][0]["content"] and "합계" not in llm.calls[0]["messages"][0]["content"]  # 시스템 프롬프트엔 숫자 요약 없음
# 대화에 근거 저장 → 다음 질문에서는 글만 history로
cid = res["conversation_id"]
conv = c.get(f"/api/conversations/{cid}", headers=G).json()
assert conv["messages"][1]["trace"][0]["tool"] == "search_transactions"
llm2 = ScriptedLLM([("text", "네")])
with patch.object(_cs, "_get_client", return_value=llm2):
    c.post("/api/chat", headers=G, json={"message": "고마워", "conversation_id": cid})
hist = llm2.calls[0]["messages"]
assert hist[2] == {"role": "assistant", "content": "10월 스타벅스는 N건이에요."} and "trace" not in hist[2]
# 목표 제안: 저장되지 않고 actions로만 나옴
from app.services import goal_service as _gs0
_deliv = _gs0.spent_so_far("agentdemo", cur)[1].get("배달", 0) + 50000
llm3 = ScriptedLLM([("tools", [("propose_goal", {"month": cur, "total_budget": 1500000, "category_limits": [{"category": "배달", "limit": _deliv}], "reason": "배달 증가"})]),
                    ("text", "아래 [적용] 버튼을 누르면 저장돼요.")])
with patch.object(_cs, "_get_client", return_value=llm3):
    res3 = c.post("/api/chat", headers=G, json={"message": "배달 한도 15만원으로 목표 잡아줘"}).json()
assert c.post("/api/chat", headers=G, json={"message": "4번째"}).status_code == 429   # 도구를 여러 번 불러도 질문 1개 = 1회
assert res3["actions"][0]["type"] == "goal_proposal" and res3["actions"][0]["total_budget"] == 1500000
assert c.get(f"/api/goals/{cur}", headers=G).json()["goal"] is None          # 저장 안 됨
# 단계 한도: 모델이 계속 도구만 부르면 5단계 후 tool_choice=none으로 답만 받음
llm4 = ScriptedLLM([("tools", [("get_monthly_summary", {"month": "2026-10"})])] * 5 + [("text", "정리하면…")])
with patch.object(_cs, "_get_client", return_value=llm4):
    res4 = _cs.chat("agentdemo", "다 알려줘")   # API 경로는 하루 한도(테스트 3회)를 이미 써서 서비스 직접 호출
assert len(llm4.calls) == 6 and llm4.calls[-1]["tool_choice"] == "none" and res4["reply"] == "정리하면…" and len(res4["trace"]) == 5
# 도구 직접 실행: 없는 도구 / JSON 아님
from app.services import agent_tools as _at
assert not _at.execute("agentdemo", "rm_rf", "{}")["ok"] and not _at.execute("agentdemo", "get_monthly_summary", "not json")["ok"]
# 비교용 baseline 모드
llm5 = ScriptedLLM([("text", "요약 기반 답변")])
with patch.object(_cs, "_get_client", return_value=llm5):
    out = _cs.chat("agentdemo", "이번 달 어때?", mode="baseline")
assert out["mode"] == "baseline" and out["trace"] == [] and "[사용자 지출 데이터 요약]" in llm5.calls[0]["messages"][0]["content"] and "tools" not in llm5.calls[0]

# 19) 목표 제안 보완: 글로만 [적용] 안내 → 검증 후 재요청, 이미 쓴 금액보다 작은 한도 거부, 추천은 쓴 금액 이상
from app.services import goal_service as _gs, agent_tools as _at
spent_total, spent_cat = _gs.spent_so_far("agentdemo", cur)
top_cat = max(spent_cat, key=spent_cat.get)
bad = _at.execute("agentdemo", "propose_goal", _json.dumps({"month": cur, "total_budget": max(10000, spent_total + 100000),
      "category_limits": [{"category": top_cat, "limit": max(1000, spent_cat[top_cat] - 1000)}], "reason": "x"}))
assert not bad["ok"] and "이미" in bad["result"]["error"], bad
sug = _gs.suggest("agentdemo", cur)
assert sug["total_budget"] >= spent_total and all(l["limit"] >= l["spent_so_far"] for l in sug["category_limits"]), sug
good_args = {"month": cur, "total_budget": sug["total_budget"], "category_limits": [{"category": l["category"], "limit": l["limit"]} for l in sug["category_limits"]], "reason": "최근 평균 기준"}
llm6 = ScriptedLLM([
    ("tools", [("get_goal_progress", {"month": cur})]),
    ("text", "총예산 180만 원을 제안해요. 아래 [적용] 버튼을 누르면 저장돼요."),   # 도구 없이 글로만 제안
    ("tools", [("propose_goal", good_args)]),                                         # 검증 메시지를 보고 도구 호출
    ("text", "제안을 만들었어요. 아래 [적용] 버튼을 누르면 저장돼요."),
])
with patch.object(_cs, "_get_client", return_value=llm6):
    out = _cs.chat("agentdemo", "이번 달 절약 목표 세워줘")
assert [t["tool"] for t in out["trace"]] == ["get_goal_progress", "self_check", "propose_goal"], out["trace"]
assert len(out["actions"]) == 1 and out["actions"][0]["total_budget"] == sug["total_budget"], out
assert "[시스템 검증]" in llm6.calls[2]["messages"][-1]["content"]
llm7 = ScriptedLLM([("text", "[적용] 버튼 안내"), ("text", "[적용] 버튼 안내")])  # 재요청은 한 번만
with patch.object(_cs, "_get_client", return_value=llm7):
    out = _cs.chat("agentdemo", "목표")
assert len(llm7.calls) == 2 and out["actions"] == []

# 20) 진행 중인 달 비교는 같은 기간(1~오늘), 한 번에 너무 많은 도구 호출은 4개까지만 실행
_d = _tk().day
cmp = _at.execute("agentdemo", "compare_months", _json.dumps({"month_a": _gs.current_month() if False else (_tk().replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m"), "month_b": cur}))
assert cmp["ok"] and f"1~{_d}일" in cmp["result"]["basis"] and cmp["result"]["month_a"]["full_month_total"] >= cmp["result"]["month_a"]["total"], cmp
assert cmp["result"]["increased"] == [d["category"] for d in cmp["result"]["category_changes"] if d["diff"] > 0]
ms = _at.execute("agentdemo", "get_monthly_summary", _json.dumps({"month": cur}))["result"]["previous_month"]
assert "same_period_total" in ms and ms["change_pct"] == _at._pct(_at.execute("agentdemo", "get_monthly_summary", _json.dumps({"month": cur}))["result"]["total"], ms["same_period_total"])
many = [("get_category_trend", {"category": c, "months": None}) for c in ["식비", "배달", "쇼핑", "교통", "카페·간식", "구독"]]
llm8 = ScriptedLLM([("tools", many), ("text", "정리")])
with patch.object(_cs, "_get_client", return_value=llm8):
    out = _cs.chat("agentdemo", "전부 추이")
assert len(out["trace"]) == 4
tool_msgs = [m for m in llm8.calls[1]["messages"] if m["role"] == "tool"]
assert len(tool_msgs) == 6 and "최대 4개" in tool_msgs[-1]["content"]   # 모든 호출 id에 응답은 돌려준다
# 21) 목표가 없어도 목표 진행 상황 도구가 월말 예상을 준다 (월 요약과 같은 값)
_gp = _at.execute("agentdemo", "get_goal_progress", _json.dumps({"month": cur}))["result"]
_ms = _at.execute("agentdemo", "get_monthly_summary", _json.dumps({"month": cur}))["result"]
if not _gp["has_goal"]:
    assert _gp["projected_month_end"] == _ms["projected_month_end"] and _gp["spent_so_far"] == _ms["total"], (_gp, _ms)
# 22) 소비 알림 카드: AI 미사용(모델 호출 0회, 하루 한도 차감 없음), 사용자 분리, 동의 필요
import unittest.mock as _um
with _um.patch.object(_cs, "_get_client", side_effect=AssertionError("insights must not call the model")):
    before = c.get("/api/me", headers=G).json().get("chat_remaining_today")
    ins = c.get("/api/insights", headers=G); assert ins.status_code == 200, ins.text
    after = c.get("/api/me", headers=G).json().get("chat_remaining_today")
assert before == after
ins = ins.json(); assert len(ins["cards"]) <= 2
for card in ins["cards"]:
    assert card["kind"] in ("goal_alert", "overspending") and card["actions"] and all(a["prompt"] for a in card["actions"])
    assert "을를" not in card["title"] and "원로" not in card["detail"]
assert c.get("/api/insights", headers=H("mallory")).json()["cards"] == []        # 비교할 3개월 데이터 없음 → 카드 없음
assert c.get("/api/insights", headers={"Authorization": "Bearer dev:nobody"}).status_code == 403   # 동의 전
from app.services.insight_service import _j
assert (_j("배달", "을", "를"), _j("식비", "을", "를"), _j("전체 지출", "이", "가")) == ("배달을", "식비를", "전체 지출이")

# 23) FR-07: 화면의 날짜 글자를 코드가 다시 읽는다 — 모델이 보이지 않는 월을 채워도 버린다
from datetime import date as _d
from app.services.upload_service import parse_date_text as _pdt, postprocess as _pp
_T = _d(2026, 11, 20)  # 금요일
assert _pdt("2026.10.28", _T) == {"year": 2026, "month": 10, "day": 28, "weekday": None}
assert _pdt("2026년 10월 28일 (수)", _T) == {"year": 2026, "month": 10, "day": 28, "weekday": "수"}
assert _pdt("10.28 (화)", _T) == {"year": None, "month": 10, "day": 28, "weekday": "화"}
assert _pdt("11월 3일", _T)["month"] == 11
assert _pdt("15일(목)", _T) == {"year": None, "month": None, "day": 15, "weekday": "목"}
assert _pdt("12일 수요일", _T) == {"year": None, "month": None, "day": 12, "weekday": "수"}
assert _pdt("11.20 14:32", _T)["day"] == 20 and _pdt("14:32", _T) is None   # 시각을 날짜로 읽지 않는다
assert _pdt("오늘", _T)["day"] == 20 and _pdt("어제 13:02", _T)["day"] == 19
assert _pdt(None, _T) is None and _pdt("13.45", _T) is None                 # 13월은 날짜가 아니다
# 모델이 '15일(목)' 행에 month=11을 지어냄 → 11/15는 일요일이라 틀림. 코드는 글자를 다시 읽어 목요일인 15일(10/15)로 정한다
_raw = {"image_type": "card_statement", "transactions": [
    {"date_text": "15일(목)", "year": None, "month": 11, "day": 15, "weekday": "목", "amount": 4500,
     "merchant": "스타벅스", "category": "카페·간식", "status": "spent", "confidence": "high"},
    {"date_text": "10.28 (화)", "year": None, "month": 10, "day": 28, "weekday": "화", "amount": 12000,
     "merchant": "김밥천국", "category": "식비", "status": "spent", "confidence": "high"},
    {"date_text": "2026.11.03", "year": 2026, "month": 11, "day": 3, "weekday": None, "amount": 30000,
     "merchant": "올리브영", "category": "장보기·생활", "status": "spent", "confidence": "high"},
    {"date_text": None, "year": None, "month": None, "day": None, "weekday": None, "amount": 5000,
     "merchant": "날짜없음", "category": "기타", "status": "spent", "confidence": "high"}]}
_out = _pp(_raw, _T, set(), {})["items"]
assert [i["date"] for i in _out] == ["2026-10-15", "2025-10-28", "2026-11-03", None], [i["date"] for i in _out]
assert any("월이 없어" in n for n in _out[0]["notes"]) and _out[0]["include"]
assert not _out[3]["include"] and any("날짜" in n for n in _out[3]["notes"])
# 글자가 없으면(구형 응답 호환) 모델이 준 칸을 쓴다
_old = {"transactions": [{"year": 2026, "month": 11, "day": 3, "weekday": None, "amount": 1000, "merchant": "x",
                          "category": "기타", "status": "spent", "confidence": "high"}]}
assert _pp(_old, _T, set(), {})["items"][0]["date"] == "2026-11-03"

# 24) AI 호출이 실패(502)하면 하루 한도를 되돌린다
from app.services.llm import ChatError as _CE
_u = "refund-user"; _H = {"Authorization": f"Bearer dev:{_u}"}
c.post("/api/me/consent", headers=_H)
def _used(field):
    from app.db import USERS as _USERS, get_store as _gstore
    return ((_gstore().get_or_none(_USERS, _u) or {}).get(field) or {}).get("count", 0)
with patch.object(_cs, "chat", side_effect=_CE("OpenAI 오류")):
    assert c.post("/api/chat", headers=_H, json={"message": "안녕"}).status_code == 502
assert _used("chat_usage") == 0
from app.services import upload_service as _us
with patch.object(_us, "extract_from_image", side_effect=_CE("Vision 오류")):
    assert c.post("/api/uploads/extract", headers=_H, json={"data_url": "data:image/png;base64,iVBORw0KGgo="}).status_code == 502
assert _used("image_usage") == 0

# 25) 날짜 묶음(sections): 머리글 아래 모든 행이 그 머리글 날짜를 받는다 (실사용 테스트: 카카오T 택시가 3/3 윗 머리글로 잡힘)
_sec = {"image_type": "card_statement", "sections": [
    {"date_text": "18일(수)", "year": None, "month": None, "day": 18, "weekday": "수", "transactions": [
        {"amount": 4800, "merchant": "스타벅스 역삼점", "category": "카페·간식", "status": "spent", "confidence": "high"},
        {"amount": 23000, "merchant": "배달의민족", "category": "배달", "status": "spent", "confidence": "high"}]},
    {"date_text": "17일(화)", "year": None, "month": None, "day": 17, "weekday": "화", "transactions": [
        {"amount": 3200, "merchant": "GS25 선릉역점", "category": "장보기·생활", "status": "spent", "confidence": "high"},
        {"amount": 12400, "merchant": "카카오T 택시", "category": "교통", "status": "spent", "confidence": "high"}]},
    {"date_text": "2026년 11월 15일(일)", "year": 2026, "month": 11, "day": 15, "weekday": "일", "transactions": [
        {"amount": 59000, "merchant": "무신사", "category": "쇼핑", "status": "spent", "confidence": "high"}]}]}
_o = _pp(_sec, _T, set(), {})["items"]
assert [(i["merchant"], i["date"]) for i in _o] == [("스타벅스 역삼점", "2026-11-18"), ("배달의민족", "2026-11-18"),
    ("GS25 선릉역점", "2026-11-17"), ("카카오T 택시", "2026-11-17"), ("무신사", "2026-11-15")], _o
assert not any("월이 없어" in n for n in _o[4]["notes"])   # 큰 머리글로 월이 보였으면 추측 안내를 붙이지 않는다
from app.services import vision_service as _vs
assert "sections" in _vs.SCHEMA["required"] and "transactions" not in _vs.SCHEMA["properties"]

# 26) 카테고리별 지난달 같은 기간 대비 (소비 요약 '지난달 대비' 목록)
_cc_rows = [{"date": "2026-10-03", "amount": 10000, "merchant": "a", "category": "식비"},
            {"date": "2026-10-20", "amount": 90000, "merchant": "b", "category": "식비"},   # 같은 기간(1~10일) 밖
            {"date": "2026-10-05", "amount": 5000, "merchant": "c", "category": "카페·간식"},
            {"date": "2026-11-04", "amount": 15000, "merchant": "d", "category": "식비"},
            {"date": "2026-11-06", "amount": 7000, "merchant": "e", "category": "배달"}]
_cc = {x["category"]: x for x in build_summary(_cc_rows, today=_d(2026, 11, 10))["current_month"]["category_compare"]}
assert _cc["식비"]["current"] == 15000 and _cc["식비"]["prev_same_period"] == 10000 and _cc["식비"]["pct"] == 50.0, _cc
assert _cc["배달"]["pct"] is None and _cc["배달"]["prev_same_period"] == 0      # 지난달 같은 기간에 없던 카테고리
assert _cc["카페·간식"]["current"] == 0 and _cc["카페·간식"]["pct"] == -100.0
print("ALL TESTS PASSED")
