import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server, db  # noqa

def client():
    server.app.testing = True
    return server.app.test_client()

def test_two_users_isolated():
    c1 = client(); c2 = client()
    c1.post("/api/register", json={"email": "u1@x.com", "password": "pw1234"})
    c2.post("/api/register", json={"email": "u2@x.com", "password": "pw1234"})
    c1.post("/api/daily-goals", json={"date": "2026-06-11", "goals": [{"title": "U1만", "blocks": 1}]})
    b1 = c1.get("/api/bootstrap?date=2026-06-11").get_json()
    b2 = c2.get("/api/bootstrap?date=2026-06-11").get_json()
    assert b1["dailyGoals"].get("2026-06-11"), "u1 goal saved"
    assert not b2["dailyGoals"].get("2026-06-11"), "u2 must not see u1 data"

def test_auth_required():
    c = client()
    assert c.get("/api/bootstrap?date=2026-06-11").status_code == 401
