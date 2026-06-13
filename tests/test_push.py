import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
os.environ["TICK_SECRET"] = "ticktest"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime, timezone, timedelta
import db, push, userstore, server  # noqa


def setup_module(m):
    db.init_db()


def _client(email):
    c = server.app.test_client()
    c.post("/api/register", json={"email": email, "password": "pw123456"})
    return c


def test_due_kinds():
    assert push.due_kinds(10, 5) == {"morning"}
    assert push.due_kinds(10, 35) == set()
    assert push.due_kinds(23, 0) == {"evening"}
    assert push.due_kinds(23, 40) == {"midnight_warn"}
    assert push.due_kinds(0, 10) == {"midnight_settle"}
    assert push.due_kinds(14, 0) == set()


def test_subscribe_and_prefs():
    c = _client("p1@p.com")
    r = c.post("/api/push/subscribe", json={"subscription": {"endpoint": "https://x/1", "keys": {}}})
    assert r.get_json()["ok"] is True
    rp = c.post("/api/push/prefs", json={"prefs": {"slot": True, "morning": False}})
    prefs = rp.get_json()["prefs"]
    assert prefs["slot"] is True and prefs["morning"] is False


def test_tick_requires_secret():
    c = server.app.test_client()
    assert c.get("/internal/tick").status_code == 403
    assert c.get("/internal/tick?key=wrong").status_code == 403


def test_tick_morning_sends(monkeypatch):
    c = _client("p2@p.com")
    c.post("/api/push/subscribe", json={"subscription": {"endpoint": "https://x/2", "keys": {}}})
    calls = []
    monkeypatch.setattr(push, "send_to_user", lambda uid, title, body, url="/": (calls.append((title, body)) or 1))
    monkeypatch.setattr(push, "kst_now", lambda: datetime(2026, 6, 14, 10, 5, tzinfo=timezone(timedelta(hours=9))))
    r = c.get("/internal/tick?key=ticktest")
    assert r.status_code == 200
    assert any("좋은 아침" in t for t, b in calls)


def test_tick_midnight_settles(monkeypatch):
    import credits
    c = _client("p3@p.com")
    c.post("/api/push/subscribe", json={"subscription": {"endpoint": "https://x/3", "keys": {}}})
    # 어제 플랜 100% → 정산 시 동결되어야
    me = c.get("/api/me").get_json()
    # uid는 세션에 있으니 서버 통해 어제 플랜 저장: urgent로 어제 날짜에 중요일정
    c.post("/api/urgent", json={"date": "2026-06-13", "items": [{"title": "어제일", "blocks": 1}]})
    boot = c.post("/api/done", json={"date": "2026-06-13", "slot": 0, "done": False})  # ensure plan saved
    monkeypatch.setattr(push, "send_to_user", lambda *a, **k: 1)
    monkeypatch.setattr(push, "kst_now", lambda: datetime(2026, 6, 14, 0, 10, tzinfo=timezone(timedelta(hours=9))))
    r = c.get("/internal/tick?key=ticktest")
    assert r.status_code == 200
    assert r.get_json()["sent"]["midnight_settle"] >= 0  # 실행되어 예외 없음


def test_dead_subscription_pruned(monkeypatch):
    uid = userstore.all_user_ids()[0] if userstore.all_user_ids() else None
    c = _client("p4@p.com")
    c.post("/api/push/subscribe", json={"subscription": {"endpoint": "https://x/dead", "keys": {}}})
    target = userstore.all_user_ids()[-1]
    monkeypatch.setattr(push, "_send_one", lambda sub, payload: False)  # 만료 시뮬
    sent = push.send_to_user(target, "t", "b")
    assert sent == 0
    p = userstore.load_json(target, "push.json", {})
    assert all(s.get("endpoint") != "https://x/dead" for s in p.get("subscriptions", []))
