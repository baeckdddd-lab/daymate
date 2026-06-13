import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db, credits  # noqa


def setup_module(m):
    db.init_db()


def _plan(types_done):
    return {"date": "2026-06-12",
            "slots": [{"slot": i, "type": t, "done": d, "label": t, "range": "10:00–10:30"}
                      for i, (t, d) in enumerate(types_done)]}


def test_achievement_pct():
    p = _plan([("grad", True), ("goal", False), ("meal", True), ("free", False)])
    assert credits.achievement(p) == (1, 2, 50)
    assert credits.achievement(_plan([("meal", True)])) == (0, 0, 0)


def test_completion_bonus():
    assert credits.completion_bonus(100) == 50
    assert credits.completion_bonus(80) == 20
    assert credits.completion_bonus(79) == 0
    assert credits.completion_bonus(60) == 0


def test_day_earned():
    p = _plan([("grad", True), ("goal", True)])   # 100% → 100 + 50
    assert credits.day_earned(p) == 150
    half = _plan([("grad", True), ("goal", False)])  # 50% → 50 + 0
    assert credits.day_earned(half) == 50


def test_streak_len():
    assert credits.streak_len([100, 70, 30, 80, 90]) == 2
    assert credits.streak_len([60, 60, 60]) == 3
    assert credits.streak_len([50]) == 0
    assert credits.streak_len([]) == 0


def test_streak_bonus():
    assert credits.streak_bonus(0) == 0
    assert credits.streak_bonus(2) == 0
    assert credits.streak_bonus(3) == 50
    assert credits.streak_bonus(7) == 200
    assert credits.streak_bonus(30) == 1600


def test_earned_total_freezes_past():
    import userstore
    u = "u-earn-1"
    userstore.save_plan(u, {"date": "2026-06-10",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": True}]})
    userstore.save_plan(u, {"date": "2026-06-12",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": False}]})
    # 과거 100%(150) + 오늘 50%(50) = 200. streak: 100→50 끊김 → 보너스 0.
    e1 = credits.earned_total(u, "2026-06-12")
    assert e1 == 200
    userstore.save_plan(u, {"date": "2026-06-10", "slots": [{"type": "grad", "done": False}]})
    assert credits.earned_total(u, "2026-06-12") == 200


def test_shop_seed_balance_buy():
    import userstore
    u = "u-shop-1"
    userstore.save_plan(u, {"date": "2026-06-12",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": True}]})
    state = credits.get_state(u, "2026-06-12")    # 100% → 150
    assert state["earned"] == 150 and state["balance"] == 150
    assert len(state["shop"]) == 9
    item_id = state["shop"][0]["id"]
    res = credits.buy(u, item_id, "2026-06-12")   # 유튜브30분 50 차감
    assert res["ok"] and res["balance"] == 100
    big = next(i for i in state["shop"] if i["price"] == 1500)["id"]
    assert credits.buy(u, big, "2026-06-12")["ok"] is False


def test_save_shop():
    import userstore
    u = "u-shop-2"
    out = credits.save_shop(u, [{"name": "라떼 한 잔", "price": 70, "emoji": "☕", "cat": "먹거리"},
                                {"name": "  ", "price": 10}])
    assert len(out) == 1 and out[0]["name"] == "라떼 한 잔" and out[0]["price"] == 70
