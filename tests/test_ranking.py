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


def _earn_100(c):
    """클라이언트 유저가 오늘 의미블록 1개 100% → 130 크레딧 적립."""
    boot = c.get("/api/bootstrap").get_json()
    today = boot["plan"]["date"]
    c.post("/api/urgent", json={"date": today, "items": [{"title": "랭킹용 일정", "blocks": 1}]})
    boot = c.get("/api/bootstrap").get_json()
    for s in boot["plan"]["slots"]:
        if s["type"] not in ("routine", "meal", "free"):
            c.post("/api/done", json={"date": today, "slot": s["slot"], "done": True})


def test_nickname_default_and_set():
    c = _client("alice@x.com")
    st = c.get("/api/credits").get_json()
    assert st["nickname"] == "alice"          # 기본값 = 이메일 로컬파트
    r = c.post("/api/nickname", json={"nickname": "앨리스짱"})
    assert r.get_json()["ok"] and r.get_json()["nickname"] == "앨리스짱"
    assert c.get("/api/credits").get_json()["nickname"] == "앨리스짱"


def test_nickname_empty_rejected():
    c = _client("bob@x.com")
    assert c.post("/api/nickname", json={"nickname": "  "}).get_json()["ok"] is False


def test_ranking_sorted_and_myrank():
    earner = _client("earner@x.com")
    _earn_100(earner)            # 130
    _client("zero@x.com")        # 0 (가입만)
    rk = earner.get("/api/ranking").get_json()
    assert rk["top"][0]["earned"] >= 130
    assert rk["top"][0]["me"] is True            # earner가 호출 → 1위가 자기
    assert rk["myRank"] == 1
    assert rk["total"] >= 2
    # earned 내림차순 보장
    earns = [r["earned"] for r in rk["top"]]
    assert earns == sorted(earns, reverse=True)


def test_ranking_requires_auth():
    assert server.app.test_client().get("/api/ranking").status_code == 401
    assert server.app.test_client().post("/api/nickname", json={"nickname": "x"}).status_code == 401
