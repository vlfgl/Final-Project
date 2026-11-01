"""인증·사용자 분리 포함 API 테스트 (DB_BACKEND=memory, 가짜 토큰 'dev:<uid>')."""
import os, sys
os.environ["DB_BACKEND"] = "memory"; os.environ["OPENAI_API_KEY"] = "test"; os.environ["DAILY_CHAT_LIMIT"] = "3"
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
assert c.get("/api/data").status_code == 401
assert c.get("/api/me").status_code == 401
assert c.get("/api/data", headers={"Authorization": "Bearer garbage"}).status_code == 401

# 2) 로그인했지만 동의 전 → 403 consent_required
me = c.get("/api/me", headers=H("alice")).json()
assert me["consented"] is False and me["email"] == "alice@test.dev", me
r = c.get("/api/data", headers=H("alice")); assert r.status_code == 403 and r.json()["detail"] == "consent_required"

# 3) 동의 후 사용 가능
assert c.post("/api/me/consent", headers=H("alice")).json()["consented"] is True
assert c.get("/api/data", headers=H("alice")).json() == []
r = c.post("/api/data", headers=H("alice"), json={"date": "2026-11-01", "value": 12000, "memo": "식비 | 점심"}); assert r.status_code == 201
alice_item = r.json()

# 4) 사용자 분리: bob은 alice 데이터를 못 보고, 수정·삭제도 못 함
c.post("/api/me/consent", headers=H("bob"))
assert c.get("/api/data", headers=H("bob")).json() == []
assert c.get("/api/data/summary", headers=H("bob")).json()["count"] == 0
assert c.put(f"/api/data/{alice_item['id']}", headers=H("bob"), json={"value": 1}).status_code == 404
assert c.delete(f"/api/data/{alice_item['id']}", headers=H("bob")).status_code == 404
assert c.get("/api/data/summary", headers=H("alice")).json()["count"] == 1

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
assert c.post("/api/me/demo", headers=ANON).json()["seeded"] == 667
assert c.post("/api/me/demo", headers=ANON).json()["seeded"] == 0
assert c.get("/api/data/summary", headers=ANON).json()["count"] == 667
assert c.post("/api/me/demo", headers=H("alice")).status_code == 400

# 7) 내 데이터 전체 삭제 → 다시 동의 필요, 데이터 0건, 다른 사용자 영향 없음
d = c.delete("/api/me", headers=H("alice")).json(); assert d["deleted"]["transactions"] == 1 and d["deleted"]["conversations"] == 3, d
assert c.get("/api/data", headers=H("alice")).status_code == 403
c.post("/api/me/consent", headers=H("alice"))
assert c.get("/api/data", headers=H("alice")).json() == []
assert c.get("/api/data/summary", headers=ANON).json()["count"] == 667

# 8) 기존 검증 유지
assert c.post("/api/data", headers=H("bob"), json={"date": "2026-13-01", "value": 1}).status_code == 422
assert c.get("/docs").status_code == 200 and c.get("/health").json() == {"status": "ok"}
r = c.options("/api/data", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
assert r.status_code == 200 and "authorization" in r.headers.get("access-control-allow-headers", "").lower()
print("ALL AUTH TESTS PASSED")
