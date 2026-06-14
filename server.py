"""친구 배포판 Flask 앱 — 멀티유저. 코어(scheduler/configlib) 재사용, userstore로 DB 저장."""
import os
from datetime import date, timedelta
from functools import wraps
from flask import Flask, request, session, jsonify, send_from_directory, Response

import db, auth, userstore, scheduler, configlib, credits, push

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
# 세션을 영속(브라우저 닫아도 유지)으로. 모바일 PWA에서 앱 닫을 때마다 로그아웃되는 것 방지.
app.permanent_session_lifetime = timedelta(days=30)
db.init_db()

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# 신규 가입자의 첫 bootstrap이 스케줄러 필수 키(gradWindow 등) 부재로
# 죽지 않도록 주는 기본 config. setupDone은 넣지 않아 setupNeeded는 True 유지.
DEFAULT_CONFIG = {
    "wake": "10:00",
    "sleep": "03:00",
    "gradWindow": {"start": "11:00", "end": "16:00", "cutoff": "22:00"},
    "fixedMeals": [
        {"name": "아침 식사", "start": "10:30", "blocks": 1},
        {"name": "점심 식사", "start": "12:00", "blocks": 2},
        {"name": "저녁 식사", "start": "19:00", "blocks": 2},
    ],
}


def login_required(fn):
    @wraps(fn)
    def wrap(*a, **k):
        if not session.get("uid"):
            return jsonify({"error": "auth required"}), 401
        return fn(*a, **k)
    return wrap


def uid():
    return session["uid"]


def resolve_date(s):
    if not s or s == "today":
        return date.today().isoformat()
    if s == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    return s


def build_plan(user_id, date_str, seed=0, base_slots=None, from_slot=0, carryover=None):
    data = userstore.load_all(user_id)
    plan = scheduler.generate(date_str, data, seed=seed, base_slots=base_slots,
                              from_slot=from_slot, carryover=carryover)
    plan["seed"] = seed
    ov = data.get("overrides", {}).get(date_str, {})
    for s in plan["slots"]:
        o = ov.get(str(s["slot"]))
        if not o:
            continue
        if o.get("label"): s["label"] = o["label"]
        if o.get("note"): s["note"] = o["note"]
        s["edited"] = True
    old = userstore.load_plan(user_id, date_str)
    if old:
        done = {s["slot"]: s.get("done") for s in old.get("slots", [])}
        for s in plan["slots"]:
            if done.get(s["slot"]):
                s["done"] = True
    userstore.save_plan(user_id, plan)
    return plan


# ---- 인증 ----
@app.post("/api/register")
def api_register():
    b = request.get_json(force=True)
    try:
        user_id = auth.register(b.get("email"), b.get("password"))
    except auth.AuthError as e:
        return jsonify({"error": str(e)}), 400
    userstore.save_json(user_id, "config.json", dict(DEFAULT_CONFIG))
    session.permanent = True
    session["uid"] = user_id
    return jsonify({"ok": True})


@app.post("/api/login")
def api_login():
    b = request.get_json(force=True)
    user_id = auth.authenticate(b.get("email"), b.get("password"))
    if not user_id:
        return jsonify({"error": "이메일/비밀번호 불일치"}), 401
    session.permanent = True
    session["uid"] = user_id
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def api_me():
    return jsonify({"loggedIn": bool(session.get("uid"))})


@app.post("/api/account/delete")
@login_required
def api_account_delete():
    """계정 영구 삭제(스토어 정책 요구). 비밀번호 재확인 후 모든 데이터 + 계정 제거."""
    b = request.get_json(force=True)
    if not auth.verify_user(uid(), b.get("password")):
        return jsonify({"error": "비밀번호가 일치하지 않습니다"}), 401
    user_id = uid()
    userstore.delete_all(user_id)
    auth.delete_user(user_id)
    session.clear()
    return jsonify({"ok": True})


# ---- 코어 API ----
@app.get("/api/bootstrap")
@login_required
def api_bootstrap():
    d = resolve_date(request.args.get("date"))
    plan = userstore.load_plan(uid(), d) or build_plan(uid(), d)
    data = userstore.load_all(uid())
    return jsonify({
        "plan": plan, "config": data["config"], "dailyGoals": data["dailyGoals"],
        "events": data["events"], "gradTasks": data["gradTasks"], "habits": data["habits"],
        "condition": data.get("conditions", {}).get(d),
        "setupNeeded": not data["config"].get("setupDone"),
    })


def _week_plans(user_id, date_str):
    """해당 주(월~일) 7일의 {date,dow,slots(full)} 리스트 + 월요일 반환."""
    base = date.fromisoformat(date_str)
    monday = base - timedelta(days=base.weekday())
    dows = ["월", "화", "수", "목", "금", "토", "일"]
    days = []
    for i in range(7):
        dd = (monday + timedelta(days=i)).isoformat()
        plan = userstore.load_plan(user_id, dd) or build_plan(user_id, dd)
        days.append({"date": dd, "dow": dows[i], "slots": plan["slots"]})
    return monday, days


@app.get("/api/week")
@login_required
def api_week():
    """주간 타임테이블(월~일 7일). 프런트 renderWeek가 days[].slots[range,label,type,done] 사용."""
    monday, days = _week_plans(uid(), resolve_date(request.args.get("date")))
    trimmed = [{"date": d["date"], "dow": d["dow"],
                "slots": [{"range": s["range"], "label": s["label"],
                           "type": s["type"], "done": s.get("done", False)}
                          for s in d["slots"]]} for d in days]
    return jsonify({"start": monday.isoformat(), "days": trimmed})


@app.get("/api/week.png")
@login_required
def api_week_png():
    """주간 타임테이블 PNG. 프런트 '주간 PNG' 버튼이 새 탭으로 연다."""
    import render_week
    monday, days = _week_plans(uid(), resolve_date(request.args.get("date")))
    png = render_week.render({"start": monday.isoformat(), "days": days})
    return Response(png, mimetype="image/png", headers={
        "Content-Disposition": f'inline; filename="week-{monday.isoformat()}.png"'})


@app.get("/api/plan.png")
@login_required
def api_plan_png():
    """일간 체크리스트 PNG. 프런트 'PNG 체크리스트' 버튼."""
    import render_plan
    d = resolve_date(request.args.get("date"))
    plan = userstore.load_plan(uid(), d) or build_plan(uid(), d)
    png = render_plan.render(plan)
    return Response(png, mimetype="image/png", headers={
        "Content-Disposition": f'inline; filename="plan-{d}.png"'})


@app.post("/api/generate")
@login_required
def api_generate():
    b = request.get_json(force=True)
    d = resolve_date(b.get("date"))
    return jsonify(build_plan(uid(), d, seed=int(b.get("seed", 0))))


@app.post("/api/replan")
@login_required
def api_replan():
    b = request.get_json(force=True)
    d = resolve_date(b.get("date"))
    old = userstore.load_plan(uid(), d) or build_plan(uid(), d)
    from_slot = scheduler.clock_to_slot(b.get("now") or "10:00")
    if from_slot >= scheduler.N_SLOTS:
        return jsonify({"ended": True, "plan": old})
    if from_slot <= 0:
        return jsonify({"plan": build_plan(uid(), d, seed=int(b.get("seed", 0)))})
    return jsonify({"plan": build_plan(uid(), d, seed=int(b.get("seed", 0)),
                                       base_slots=old["slots"], from_slot=from_slot,
                                       carryover=b.get("carryover") or [])})


@app.post("/api/condition")
@login_required
def api_condition():
    b = request.get_json(force=True)
    d = resolve_date(b.get("date"))
    mood = max(1, min(5, int(b.get("mood", 3))))
    energy = max(1, min(5, int(b.get("energy", 3))))
    cond = {"mood": mood, "energy": energy,
            "intensity": scheduler.intensity_from(mood, energy), "source": "morning"}
    conds = userstore.load_json(uid(), "conditions.json", {})
    conds[d] = cond
    userstore.save_json(uid(), "conditions.json", conds)
    return jsonify({"plan": build_plan(uid(), d), "condition": cond})


@app.post("/api/habits")
@login_required
def api_habits():
    b = request.get_json(force=True)
    habits = configlib.normalize_habits(b.get("habits"))
    userstore.save_json(uid(), "habits.json", habits)
    return jsonify({"ok": True, "habits": habits})


@app.post("/api/setup")
@login_required
def api_setup():
    b = request.get_json(force=True)
    d = resolve_date(b.get("date"))
    cfg = userstore.load_json(uid(), "config.json", {})
    patch = dict(b.get("config") or {}); patch["setupDone"] = True
    cfg = configlib.merge_config_patch(cfg, patch)
    userstore.save_json(uid(), "config.json", cfg)
    userstore.save_json(uid(), "habits.json", configlib.normalize_habits(b.get("habits")))
    return jsonify({"plan": build_plan(uid(), d), "config": cfg})


@app.post("/api/daily-goals")
@login_required
def api_daily_goals():
    b = request.get_json(force=True)
    dg = userstore.load_json(uid(), "daily-goals.json", {})
    dg[b["date"]] = b["goals"]
    userstore.save_json(uid(), "daily-goals.json", dg)
    return jsonify({"ok": True})


@app.post("/api/events")
@login_required
def api_events():
    b = request.get_json(force=True)
    ev = userstore.load_json(uid(), "events.json", {})
    ev.setdefault(b["date"], []).append(b["event"])
    userstore.save_json(uid(), "events.json", ev)
    return jsonify(build_plan(uid(), b["date"]))


def _today():
    return resolve_date("today")


@app.get("/api/credits")
@login_required
def api_credits():
    return jsonify(credits.get_state(uid(), _today()))


@app.post("/api/credits/buy")
@login_required
def api_credits_buy():
    b = request.get_json(force=True)
    return jsonify(credits.buy(uid(), b.get("itemId"), _today()))


@app.post("/api/credits/shop")
@login_required
def api_credits_shop():
    b = request.get_json(force=True)
    return jsonify({"shop": credits.save_shop(uid(), b.get("shop") or [])})


@app.post("/api/nickname")
@login_required
def api_nickname():
    b = request.get_json(force=True)
    return jsonify(credits.set_nickname(uid(), b.get("nickname")))


@app.get("/api/ranking")
@login_required
def api_ranking():
    return jsonify(credits.ranking(_today(), uid()))


@app.post("/api/done")
@login_required
def api_done():
    b = request.get_json(force=True)
    d = resolve_date(b.get("date"))
    plan = userstore.load_plan(uid(), d)
    if plan:
        for s in plan["slots"]:
            if s["slot"] == b["slot"]:
                s["done"] = bool(b["done"])
        userstore.save_plan(uid(), plan)
    state = credits.get_state(uid(), d)
    celebrate = "100" if state["today"]["achievement"] >= 100 else None
    if celebrate == "100":
        try:
            if push.should_send_reward(uid(), d):
                coins = state["today"]["earned"]
                t = push.MSG["reward"][0]
                push.send_to_user(uid(), t, push.MSG["reward"][1].format(coins=coins))
        except Exception:
            pass  # 푸시 실패가 체크 동작을 막지 않게
    return jsonify({"ok": True, "credits": state, "celebrate": celebrate})


TICK_SECRET = os.environ.get("TICK_SECRET", "")


@app.get("/api/push/key")
@login_required
def api_push_key():
    return jsonify({"key": push.VAPID_PUBLIC})


@app.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    b = request.get_json(force=True)
    sub = b.get("subscription") or b
    push.add_subscription(uid(), sub)
    return jsonify({"ok": True})


@app.post("/api/push/prefs")
@login_required
def api_push_prefs():
    b = request.get_json(force=True)
    return jsonify({"prefs": push.set_prefs(uid(), b.get("prefs") or {})})


@app.post("/api/push/test")
@login_required
def api_push_test():
    n = push.send_to_user(uid(), "🔔 테스트 알림", "알림이 정상 작동해요!")
    return jsonify({"ok": True, "sent": n})


@app.get("/internal/tick")
def internal_tick():
    secret = os.environ.get("TICK_SECRET", "") or TICK_SECRET
    if not secret or request.args.get("key") != secret:
        return jsonify({"error": "forbidden"}), 403
    now = push.kst_now()
    kinds = push.due_kinds(now.hour, now.minute)
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    cur_slot = scheduler.clock_to_slot(now.strftime("%H:%M"))
    sent = {"morning": 0, "evening": 0, "midnight_warn": 0, "midnight_settle": 0, "slot": 0}
    for u in userstore.all_user_ids():
        p = push.get_push(u)
        if not p["subscriptions"]:
            continue
        prefs = p["prefs"]
        if "morning" in kinds and prefs.get("morning"):
            t, b = push.MSG["morning"]
            sent["morning"] += push.send_to_user(u, t, b)
        if "evening" in kinds and prefs.get("evening"):
            t, b = push.MSG["evening"]
            sent["evening"] += push.send_to_user(u, t, b)
        if "midnight_warn" in kinds and prefs.get("midnight"):
            t, b = push.MSG["midnight_warn"]
            sent["midnight_warn"] += push.send_to_user(u, t, b)
        if "midnight_settle" in kinds and prefs.get("midnight"):
            yplan = userstore.load_plan(u, yesterday) or {"slots": []}
            _, _, pct = credits.achievement(yplan)
            coins = credits.day_earned(yplan)
            credits.earned_total(u, today)   # 어제를 settled에 동결
            t = push.MSG["midnight_settle"][0]
            b = push.MSG["midnight_settle"][1].format(pct=pct, coins=coins)
            sent["midnight_settle"] += push.send_to_user(u, t, b)
        if prefs.get("slot"):
            plan = userstore.load_plan(u, today)
            if plan and 0 <= cur_slot < len(plan.get("slots", [])):
                s = plan["slots"][cur_slot]
                if s and s.get("type") not in credits.MEANINGLESS_TYPES and not s.get("done"):
                    t = push.MSG["slot"][0]
                    b = push.MSG["slot"][1].format(label=s.get("label", ""))
                    sent["slot"] += push.send_to_user(u, t, b)
    return jsonify({"ok": True, "kst": now.strftime("%Y-%m-%d %H:%M"), "sent": sent})


@app.post("/api/self-dev")
@login_required
def api_self_dev():
    b = request.get_json(force=True)
    sd = userstore.load_json(uid(), "self-dev.json", {})
    tasks = [t.strip() for t in b.get("tasks", []) if t.strip()][:3]
    if tasks:
        sd[b["date"]] = tasks
    else:
        sd.pop(b["date"], None)
    userstore.save_json(uid(), "self-dev.json", sd)
    return jsonify(build_plan(uid(), b["date"]))


@app.post("/api/urgent")
@login_required
def api_urgent():
    b = request.get_json(force=True)
    dg = userstore.load_json(uid(), "daily-goals.json", {})
    # 기존 일반(비긴급) 목표는 유지, 긴급만 교체
    day = [g for g in dg.get(b["date"], []) if not g.get("important")]
    for it in b.get("items", []):
        title = (it.get("title") or "").strip()
        if title:
            day.append({"title": title,
                        "blocks": max(1, min(4, int(it.get("blocks", 1)))),
                        "important": True})
    if day:
        dg[b["date"]] = day
    else:
        dg.pop(b["date"], None)
    userstore.save_json(uid(), "daily-goals.json", dg)
    return jsonify(build_plan(uid(), b["date"]))


@app.post("/api/daily-goals/delete")
@login_required
def api_daily_goals_delete():
    b = request.get_json(force=True)
    dg = userstore.load_json(uid(), "daily-goals.json", {})
    lst = dg.get(b["date"], [])
    idx = int(b.get("index", -1))
    if 0 <= idx < len(lst):
        lst.pop(idx)
        if lst:
            dg[b["date"]] = lst
        else:
            dg.pop(b["date"], None)
        userstore.save_json(uid(), "daily-goals.json", dg)
    return jsonify({"ok": True})


@app.post("/api/events/delete")
@login_required
def api_events_delete():
    b = request.get_json(force=True)
    ev = userstore.load_json(uid(), "events.json", {})
    lst = ev.get(b["date"], [])
    idx = int(b.get("index", -1))
    if 0 <= idx < len(lst):
        lst.pop(idx)
        if lst:
            ev[b["date"]] = lst
        else:
            ev.pop(b["date"], None)
        userstore.save_json(uid(), "events.json", ev)
    return jsonify({"ok": True})


@app.post("/api/slot")
@login_required
def api_slot():
    b = request.get_json(force=True)
    ov = userstore.load_json(uid(), "overrides.json", {})
    d = b["date"]
    slot = str(int(b["slot"]))
    day = ov.get(d, {})
    if b.get("reset"):
        day.pop(slot, None)
    else:
        entry = {}
        if (b.get("label") or "").strip():
            entry["label"] = b["label"].strip()
        if (b.get("note") or "").strip():
            entry["note"] = b["note"].strip()
        if entry:
            day[slot] = entry
        else:
            day.pop(slot, None)
    if day:
        ov[d] = day
    else:
        ov.pop(d, None)
    userstore.save_json(uid(), "overrides.json", ov)
    return jsonify(build_plan(uid(), d))


@app.get("/privacy")
@app.get("/privacy.html")
def privacy():
    """개인정보처리방침 + 계정 삭제 안내 (Play Console 'privacy/계정삭제 URL' 충족용).
    로그인 없이 공개 접근. 기존 static/privacy.html을 재사용하되 CONTACT_EMAIL
    플레이스홀더를 env 값으로 자동 치환 — 수동 교체 누락(런북 C-7 footgun) 방지."""
    with open(os.path.join(STATIC, "privacy.html"), encoding="utf-8") as f:
        html = f.read()
    contact = os.environ.get("CONTACT_EMAIL")
    if contact:
        html = html.replace("CONTACT_EMAIL (운영자 이메일 기재 예정)", contact)
    return Response(html, mimetype="text/html")


@app.get("/")
def index():
    if not session.get("uid"):
        return send_from_directory(STATIC, "login.html")
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:fn>")
def static_files(fn):
    return send_from_directory(STATIC, fn)


@app.get("/<path:fn>")
def root_files(fn):
    return send_from_directory(STATIC, fn)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8800)))
