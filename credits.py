"""크레딧 계산·잔고·보상샵 (순수 로직 + userstore 연계).

파생형: earned는 플랜에서 계산, spent는 원장. 과거 날짜는 동결(settle)되어
이후 그 날짜를 수정해도 크레딧이 변하지 않는다(자정 마감 = 타이밍 강제).
"""
import time

import db
import userstore

MEANINGLESS_TYPES = {"routine", "meal", "free"}
BLOCK_CREDIT = 10
MILESTONES = {3: 50, 7: 150, 14: 400, 30: 1000}

SEED_SHOP = [
    {"id": "s1", "name": "유튜브 30분", "price": 50, "emoji": "🛋", "cat": "휴식"},
    {"id": "s2", "name": "낮잠 1시간", "price": 80, "emoji": "🛋", "cat": "휴식"},
    {"id": "s3", "name": "게임 1시간", "price": 120, "emoji": "🛋", "cat": "휴식"},
    {"id": "s4", "name": "디저트/간식", "price": 100, "emoji": "🍗", "cat": "먹거리"},
    {"id": "s5", "name": "배달음식", "price": 300, "emoji": "🍗", "cat": "먹거리"},
    {"id": "s6", "name": "치킨", "price": 400, "emoji": "🍗", "cat": "먹거리"},
    {"id": "s7", "name": "영화 한 편", "price": 200, "emoji": "🎁", "cat": "큰보상"},
    {"id": "s8", "name": "갖고싶던 거 사기", "price": 1000, "emoji": "🎁", "cat": "큰보상"},
    {"id": "s9", "name": "하루 휴가", "price": 1500, "emoji": "🎁", "cat": "큰보상"},
]


# ---- 순수 계산 ----
def _meaningful(slots):
    return [s for s in slots if s.get("type") not in MEANINGLESS_TYPES]


def block_credits(plan):
    return BLOCK_CREDIT * sum(1 for s in _meaningful(plan.get("slots", [])) if s.get("done"))


def achievement(plan):
    m = _meaningful(plan.get("slots", []))
    total = len(m)
    done = sum(1 for s in m if s.get("done"))
    pct = round(done / total * 100) if total else 0
    return done, total, pct


def tier_bonus(pct):
    if pct >= 100:
        return 120
    if pct >= 80:
        return 60
    if pct >= 60:
        return 30
    return 0


def day_earned(plan):
    _, _, pct = achievement(plan)
    return block_credits(plan) + tier_bonus(pct)


def streak_len(pcts):
    """pcts: 오래된→최근 순 달성률. 최근부터 연속된 달성일(pct>=60) 수."""
    n = 0
    for pct in reversed(pcts):
        if pct >= 60:
            n += 1
        else:
            break
    return n


def streak_bonus(max_streak):
    return sum(b for m, b in MILESTONES.items() if m <= max_streak)


# ---- 적립 합산 (오늘 실시간 / 과거 동결) ----
def earned_total(user_id, today):
    settled = userstore.load_json(user_id, "settled.json", {})
    days = settled.get("days", {})
    max_streak = settled.get("maxStreak", 0)
    dates = [d for d in userstore.list_plan_dates(user_id) if d <= today]
    total = 0
    pcts = []
    dirty = False
    for d in dates:
        plan = userstore.load_plan(user_id, d) or {"slots": []}
        _, _, pct = achievement(plan)
        pcts.append(pct)
        if d < today:
            if d not in days:
                days[d] = day_earned(plan)   # 동결
                dirty = True
            total += days[d]
        else:
            total += day_earned(plan)         # 오늘 실시간
    eff = max(max_streak, streak_len(pcts))
    if eff > max_streak:
        max_streak = eff
        dirty = True
    if dirty:
        settled["days"] = days
        settled["maxStreak"] = max_streak
        userstore.save_json(user_id, "settled.json", settled)
    return total + streak_bonus(eff)


# ---- 보상샵 / 잔고 ----
def _load(user_id):
    c = userstore.load_json(user_id, "credits.json", {})
    if "shop" not in c:
        c["shop"] = [dict(x) for x in SEED_SHOP]
    c.setdefault("spent", [])
    return c


def get_state(user_id, today):
    c = _load(user_id)
    earned = earned_total(user_id, today)
    spent_sum = sum(int(x["price"]) for x in c["spent"])
    plan = userstore.load_plan(user_id, today) or {"slots": []}
    done, total, pct = achievement(plan)
    settled = userstore.load_json(user_id, "settled.json", {})
    return {
        "earned": earned, "spent": spent_sum, "balance": earned - spent_sum,
        "today": {"done": done, "total": total, "achievement": pct,
                  "blockCredits": block_credits(plan), "tier": tier_bonus(pct)},
        "streak": settled.get("maxStreak", 0),
        "shop": c["shop"], "spentLog": c["spent"][-20:],
        "nickname": get_nickname(user_id),
    }


def buy(user_id, item_id, today):
    c = _load(user_id)
    item = next((i for i in c["shop"] if i["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": "보상을 찾을 수 없어요"}
    earned = earned_total(user_id, today)
    balance = earned - sum(int(x["price"]) for x in c["spent"])
    if balance < int(item["price"]):
        return {"ok": False, "error": "크레딧이 부족해요", "balance": balance}
    c["spent"].append({"ts": int(time.time()), "itemId": item_id,
                       "name": item["name"], "price": int(item["price"])})
    userstore.save_json(user_id, "credits.json", c)
    return {"ok": True, "balance": balance - int(item["price"])}


def _default_nick(user_id):
    with db.SessionLocal() as s:
        u = s.query(db.User).filter_by(id=user_id).one_or_none()
    if u and u.email:
        return u.email.split("@")[0][:20]
    return f"친구{user_id}"


def get_nickname(user_id):
    c = userstore.load_json(user_id, "credits.json", {})
    nick = (c.get("nickname") or "").strip()
    return nick or _default_nick(user_id)


def set_nickname(user_id, name):
    name = (name or "").strip()[:20]
    if not name:
        return {"ok": False, "error": "닉네임을 입력하세요"}
    c = _load(user_id)
    c["nickname"] = name
    userstore.save_json(user_id, "credits.json", c)
    return {"ok": True, "nickname": name}


def ranking(today, me):
    """전체 유저의 누적 earned(소비 무관) 내림차순. 상위 20 + 내 등수."""
    rows = []
    for u in userstore.all_user_ids():
        rows.append({"uid": u, "nickname": get_nickname(u), "earned": earned_total(u, today)})
    rows.sort(key=lambda r: (-r["earned"], r["nickname"]))
    top, my_rank = [], None
    for i, r in enumerate(rows, 1):
        if r["uid"] == me:
            my_rank = i
        if i <= 20:
            top.append({"rank": i, "nickname": r["nickname"],
                        "earned": r["earned"], "me": r["uid"] == me})
    return {"top": top, "myRank": my_rank, "total": len(rows)}


def save_shop(user_id, shop):
    """shop 전체 목록 교체(추가/수정/삭제). 각 항목 {id,name,price,emoji,cat}."""
    c = _load(user_id)
    clean = []
    for it in shop:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        clean.append({"id": str(it.get("id") or f"u{int(time.time() * 1000) % 100000}{len(clean)}"),
                      "name": name, "price": max(0, int(it.get("price", 0))),
                      "emoji": it.get("emoji", "🎁"), "cat": it.get("cat", "기타")})
    c["shop"] = clean
    userstore.save_json(user_id, "credits.json", c)
    return clean
