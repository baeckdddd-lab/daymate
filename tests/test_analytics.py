import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
os.environ["TICK_SECRET"] = "ticktest"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime
import db, analytics, server  # noqa


def setup_module(m):
    db.init_db()


def test_mark_active_dedup():
    analytics.mark_active(9001, "2026-06-14")
    analytics.mark_active(9001, "2026-06-14")  # 중복 무시
    with db.SessionLocal() as s:
        n = s.query(db.ActiveDay).filter_by(user_id=9001, day="2026-06-14").count()
    assert n == 1


def test_stats_counts_active_via_request():
    c = server.app.test_client()
    c.post("/api/register", json={"email": "act1@a.com", "password": "pw123456"})
    c.get("/api/credits")  # login_required → mark_active 오늘
    stats = analytics.compute_stats()
    assert stats["users_total"] >= 1
    assert stats["dau"] >= 1


def test_cohort_retention():
    with db.SessionLocal() as s:
        u = db.User(email="old@x.com", pw_hash="x", created=datetime(2026, 6, 1, 12, 0))
        s.add(u); s.commit(); uid = u.id
        s.add(db.ActiveDay(user_id=uid, day="2026-06-08"))  # created+7
        s.commit()
    stats = analytics.compute_stats("2026-06-14")
    assert stats["retention"]["D7"]["eligible"] >= 1
    assert stats["retention"]["D7"]["retained"] >= 1


def test_activation_funnel():
    c = server.app.test_client()
    c.post("/api/register", json={"email": "actv@a.com", "password": "pw123456"})
    c.post("/api/setup", json={"date": "today", "config": {}, "habits": []})  # 온보딩 완료
    stats = analytics.compute_stats()
    assert stats["activated"] >= 1
    assert "first_day_achieved" in stats and "activated_pct" in stats


def test_stats_endpoint_key_gate():
    c = server.app.test_client()
    assert c.get("/internal/stats").status_code == 403
    assert c.get("/internal/stats?key=wrong").status_code == 403
    r = c.get("/internal/stats?key=ticktest")
    assert r.status_code == 200 and "retention" in r.get_json()
