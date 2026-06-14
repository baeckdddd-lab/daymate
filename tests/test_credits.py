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
    # 과거 100%(150) + 오늘 50%(50), 각 날짜 보너스 배율 적용. streak: 100→50 끊김 → 0.
    m10 = credits.bonus_multiplier(u, "2026-06-10")
    m12 = credits.bonus_multiplier(u, "2026-06-12")
    expected = 150 * m10 + 50 * m12
    e1 = credits.earned_total(u, "2026-06-12")
    assert e1 == expected
    userstore.save_plan(u, {"date": "2026-06-10", "slots": [{"type": "grad", "done": False}]})
    assert credits.earned_total(u, "2026-06-12") == expected   # 과거 동결


def test_shop_seed_balance_buy():
    import userstore
    u = "u-shop-1"
    userstore.save_plan(u, {"date": "2026-06-12",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": True}]})
    exp = 150 * credits.bonus_multiplier(u, "2026-06-12")   # 100% × 보너스배율
    state = credits.get_state(u, "2026-06-12")
    assert state["earned"] == exp and state["balance"] == exp
    assert len(state["shop"]) == 9
    item_id = state["shop"][0]["id"]
    res = credits.buy(u, item_id, "2026-06-12")   # 유튜브30분 50 차감
    assert res["ok"] and res["balance"] == exp - 50
    big = next(i for i in state["shop"] if i["price"] == 1500)["id"]
    assert credits.buy(u, big, "2026-06-12")["ok"] is False


def test_bonus_multiplier():
    # 결정적(재호출 동일) + 1과 2 둘 다 발생
    vals = {credits.bonus_multiplier("u-bonus", f"2026-06-{d:02d}") for d in range(1, 29)}
    assert vals <= {1, 2} and 1 in vals and 2 in vals
    assert credits.bonus_multiplier("u-bonus", "2026-06-14") == credits.bonus_multiplier("u-bonus", "2026-06-14")


def test_bonus_day_doubles_earned():
    import userstore
    u = "u-bonusday"
    # u의 보너스 데이인 날짜 하나 찾기
    bd = next(f"2026-07-{d:02d}" for d in range(1, 29) if credits.bonus_multiplier(u, f"2026-07-{d:02d}") == 2)
    userstore.save_plan(u, {"date": bd, "slots": [{"type": "grad", "done": True}]})  # 100%=150
    st = credits.get_state(u, bd)
    assert st["today"]["bonusDay"] is True
    assert st["today"]["earned"] == 300   # 150 × 2


def test_current_streak_calendar():
    import userstore
    u = "u-cs-1"
    for d in ("2026-06-12", "2026-06-13"):
        userstore.save_plan(u, {"date": d, "slots": [{"type": "grad", "done": True}]})  # 100%
    userstore.save_plan(u, {"date": "2026-06-14",
        "slots": [{"type": "grad", "done": True}, {"type": "goal", "done": False}]})    # 50%
    cs = credits.current_streak(u, "2026-06-14")
    assert cs["streak"] == 2 and cs["todayAchieved"] is False and cs["atRisk"] is True
    userstore.save_plan(u, {"date": "2026-06-14", "slots": [{"type": "grad", "done": True}]})
    cs2 = credits.current_streak(u, "2026-06-14")
    assert cs2["streak"] == 3 and cs2["todayAchieved"] is True and cs2["atRisk"] is False


def test_current_streak_gap_breaks():
    import userstore
    u = "u-cs-2"
    userstore.save_plan(u, {"date": "2026-06-10", "slots": [{"type": "grad", "done": True}]})
    userstore.save_plan(u, {"date": "2026-06-12", "slots": [{"type": "grad", "done": True}]})
    cs = credits.current_streak(u, "2026-06-12")  # 어제(06-11) 빈날 → 끊김
    assert cs["streak"] == 1


def test_save_shop():
    import userstore
    u = "u-shop-2"
    out = credits.save_shop(u, [{"name": "라떼 한 잔", "price": 70, "emoji": "☕", "cat": "먹거리"},
                                {"name": "  ", "price": 10}])
    assert len(out) == 1 and out[0]["name"] == "라떼 한 잔" and out[0]["price"] == 70
