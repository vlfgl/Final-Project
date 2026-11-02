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
    m.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="테스트 답변"))]
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

# 6) 체험(익명) 계정: 동의 → 샘플 데이터 667건, 두 번 호출해도 중복 없음, 일반 계정은 불가
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
print("ALL TESTS PASSED")
