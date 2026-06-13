import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db, server  # noqa


def setup_module(m):
    db.init_db()


def _client(email):
    c = server.app.test_client()
    c.post("/api/register", json={"email": email, "password": "pw123456"})
    return c


def test_credits_endpoint_and_buy():
    c = _client("c1@c.com")
    r = c.get("/api/credits")
    assert r.status_code == 200
    j = r.get_json()
    assert "balance" in j and "shop" in j and len(j["shop"]) == 9
    item = j["shop"][0]["id"]
    rb = c.post("/api/credits/buy", json={"itemId": item})
    assert rb.get_json()["ok"] is False  # 잔고 0


def test_shop_edit():
    c = _client("c2@c.com")
    r = c.post("/api/credits/shop", json={"shop": [
        {"name": "라떼 한 잔", "price": 70, "emoji": "☕", "cat": "먹거리"}]})
    assert r.status_code == 200
    assert len(r.get_json()["shop"]) == 1


def test_credits_requires_auth():
    c = server.app.test_client()
    assert c.get("/api/credits").status_code == 401


def test_done_returns_credits():
    c = _client("c3@c.com")
    c.post("/api/generate", json={"date": "today"})
    boot = c.get("/api/bootstrap").get_json()
    slot = boot["plan"]["slots"][0]   # 응답 계약만 검증(의미블록 로직은 test_credits)
    r = c.post("/api/done", json={"slot": slot["slot"], "done": True})
    j = r.get_json()
    assert j["ok"] is True
    assert "credits" in j and "balance" in j["credits"]
    assert j["credits"]["today"]["achievement"] >= 0
    assert "celebrate" in j


def test_plan_png():
    c = _client("png@c.com")
    c.post("/api/generate", json={"date": "today"})
    r = c.get("/api/plan.png?date=today")
    assert r.status_code == 200 and r.mimetype == "image/png"
    body = r.get_data()
    assert body[:8] == b"\x89PNG\r\n\x1a\n" and len(body) > 2000


def test_multiuser_isolation():
    a = _client("iso-a@c.com")
    b = _client("iso-b@c.com")
    # a가 샵 편집 → b는 기본 9종 그대로
    a.post("/api/credits/shop", json={"shop": [{"name": "A만보임", "price": 10}]})
    assert len(b.get("/api/credits").get_json()["shop"]) == 9
