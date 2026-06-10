import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db, userstore  # noqa

def setup_module(m):
    db.init_db()

def test_save_and_load_json_per_user():
    userstore.save_json(1, "daily-goals.json", {"2026-06-11": [{"title": "A"}]})
    userstore.save_json(2, "daily-goals.json", {"2026-06-11": [{"title": "B"}]})
    assert userstore.load_json(1, "daily-goals.json", {})["2026-06-11"][0]["title"] == "A"
    assert userstore.load_json(2, "daily-goals.json", {})["2026-06-11"][0]["title"] == "B"

def test_load_all_shape_matches_core():
    userstore.save_json(1, "config.json", {"wake": "09:00"})
    data = userstore.load_all(1)
    for k in ("config","goals","habits","tasks","gradTasks","dailyGoals",
              "events","selfDev","fillers","overrides","conditions"):
        assert k in data
    assert data["config"]["wake"] == "09:00"

def test_plan_roundtrip():
    userstore.save_plan(1, {"date": "2026-06-11", "slots": [{"slot": 0}]})
    assert userstore.load_plan(1, "2026-06-11")["slots"][0]["slot"] == 0
    assert userstore.load_plan(1, "2099-01-01") is None
