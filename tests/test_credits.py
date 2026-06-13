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


def test_meaningful_and_block_credits():
    p = _plan([("grad", True), ("meal", True), ("free", True),
               ("routine", True), ("goal", True), ("selfdev", False)])
    assert credits.block_credits(p) == 20


def test_achievement_pct():
    p = _plan([("grad", True), ("goal", False), ("meal", True), ("free", False)])
    assert credits.achievement(p) == (1, 2, 50)
    assert credits.achievement(_plan([("meal", True)])) == (0, 0, 0)


def test_tier_bonus():
    assert credits.tier_bonus(100) == 120
    assert credits.tier_bonus(80) == 60
    assert credits.tier_bonus(79) == 30
    assert credits.tier_bonus(60) == 30
    assert credits.tier_bonus(59) == 0


def test_day_earned():
    p = _plan([("grad", True), ("goal", True)])
    assert credits.day_earned(p) == 140


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
    e1 = credits.earned_total(u, "2026-06-12")
    assert e1 == 150
    userstore.save_plan(u, {"date": "2026-06-10", "slots": [{"type": "grad", "done": False}]})
    assert credits.earned_total(u, "2026-06-12") == 150


def test_shop_seed_balance_buy():
    import userstore
    u = "u-shop-1"
    userstore.save_plan(u, {"date": "2026-06-12",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": True}]})
    state = credits.get_state(u, "2026-06-12")
    assert state["earned"] == 140 and state["balance"] == 140
    assert len(state["shop"]) == 9
    item_id = state["shop"][0]["id"]
    res = credits.buy(u, item_id, "2026-06-12")
    assert res["ok"] and res["balance"] == 90
    big = next(i for i in state["shop"] if i["price"] == 1500)["id"]
    assert credits.buy(u, big, "2026-06-12")["ok"] is False


def test_save_shop():
    import userstore
    u = "u-shop-2"
    out = credits.save_shop(u, [{"name": "라떼 한 잔", "price": 70, "emoji": "☕", "cat": "먹거리"},
                                {"name": "  ", "price": 10}])
    assert len(out) == 1 and out[0]["name"] == "라떼 한 잔" and out[0]["price"] == 70
