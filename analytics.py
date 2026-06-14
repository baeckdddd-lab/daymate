"""리텐션·활성 측정 (이벤트 로깅 + 집계). 솔로 메이커가 숫자로 판단하기 위함."""
from collections import defaultdict
from datetime import date, timedelta

import db
import userstore


def mark_active(user_id, day=None):
    """유저의 '오늘 활동' 기록(중복은 무시). login_required 모든 요청에서 호출."""
    day = day or date.today().isoformat()
    with db.SessionLocal() as s:
        if s.get(db.ActiveDay, (user_id, day)):
            return
        s.add(db.ActiveDay(user_id=user_id, day=day))
        try:
            s.commit()
        except Exception:
            s.rollback()


def _count_subscribed():
    n = 0
    for u in userstore.all_user_ids():
        p = userstore.load_json(u, "push.json", {})
        if p.get("subscriptions"):
            n += 1
    return n


def compute_stats(today=None):
    today = today or date.today().isoformat()
    t = date.fromisoformat(today)
    with db.SessionLocal() as s:
        users = s.query(db.User.id, db.User.created).all()
        actives = s.query(db.ActiveDay.user_id, db.ActiveDay.day).all()

    active_by_user = defaultdict(set)
    active_by_day = defaultdict(set)
    for uid, day in actives:
        active_by_user[uid].add(day)
        active_by_day[day].add(uid)

    def active_within(days):
        cutoff = (t - timedelta(days=days - 1)).isoformat()
        return len({uid for uid, day in actives if day >= cutoff})

    def cohort(n):
        elig = [(uid, c) for uid, c in users if c and (t - c.date()).days >= n]
        if not elig:
            return {"eligible": 0, "retained": 0, "pct": None}
        hit = sum(1 for uid, c in elig
                  if (c.date() + timedelta(days=n)).isoformat() in active_by_user.get(uid, ()))
        return {"eligible": len(elig), "retained": hit, "pct": round(hit / len(elig) * 100)}

    signups = defaultdict(int)
    for _, c in users:
        if c:
            signups[c.date().isoformat()] += 1

    last14 = [(t - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    streaks = []
    for u in userstore.all_user_ids():
        st = userstore.load_json(u, "settled.json", {}).get("maxStreak", 0)
        streaks.append(st)

    # 활성화 퍼널: 온보딩 완료(setupDone) + 가입 첫날 달성(>=60%)
    import credits as _credits
    activated, first_day_hit = 0, 0
    for uid_, created in users:
        if userstore.load_json(uid_, "config.json", {}).get("setupDone"):
            activated += 1
        if created:
            fp = userstore.load_plan(uid_, created.date().isoformat())
            if fp:
                _, _, fp_pct = _credits.achievement(fp)
                if fp_pct >= 60:
                    first_day_hit += 1

    return {
        "today": today,
        "users_total": len(users),
        "dau": active_within(1),
        "wau": active_within(7),
        "mau": active_within(30),
        "retention": {"D1": cohort(1), "D7": cohort(7), "D30": cohort(30)},
        "push_opt_in": _count_subscribed(),
        "signups_by_day": {d: signups.get(d, 0) for d in last14},
        "active_by_day": {d: len(active_by_day.get(d, ())) for d in last14},
        "max_streak_avg": round(sum(streaks) / len(streaks), 1) if streaks else 0,
        "streak_3plus": sum(1 for x in streaks if x >= 3),
        "activated": activated,
        "activated_pct": round(activated / len(users) * 100) if users else 0,
        "first_day_achieved": first_day_hit,
    }
