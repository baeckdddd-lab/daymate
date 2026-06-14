"""데일리 플래너 스케줄링 엔진 (결정적).

규칙:
- 10:00 기상 ~ 03:00 취침, 30분 슬롯 34개
- (중요) 항목 최우선: 모든 규칙보다 먼저 배치
- 11:00~16:00 대학원 전용 (점심만 예외)
- 대학원은 16시 이후도 계속, 단 22:00 이후 금지
- 같은 작업 연속 금지 (운동·식사·고정일정·중요는 예외)
- 자유/여유 하루 1시간(2블록)
- filler: 독서(1), 릴스 편집(2) 반복
"""

from datetime import date as _date

WAKE_MIN = 10 * 60  # 10:00
N_SLOTS = 34        # 10:00 ~ 03:00


def habit_on_day(h, weekday):
    """요일별 루틴 — days(0=월..6=일)가 있으면 그 요일만, 없으면 매일(기존 동작)."""
    days = h.get("days")
    return (weekday in days) if days else True


# ---- 컨디션 → 강도 ----
def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def intensity_from(mood, energy):
    """기분·에너지(각 1~5) → 강도 30~100 (에너지 60% + 기분 40% 가중)."""
    e = (clamp(energy, 1, 5) - 1) / 4
    m = (clamp(mood, 1, 5) - 1) / 4
    return round(clamp((e * 0.6 + m * 0.4) * 70 + 30, 30, 100))


def intensity_for(data, date_str):
    """해당 날짜의 강도. 컨디션 미설정이면 None(=기존 동작 유지)."""
    c = data.get("conditions", {}).get(date_str)
    if not c:
        return None
    if c.get("intensity") is not None:
        return c["intensity"]
    if c.get("mood") and c.get("energy"):
        return intensity_from(c["mood"], c["energy"])
    return None


def free_blocks_for(intensity):
    """강도 30%→4블록, ~65%→2, 100%→1."""
    return int(clamp(round(4 - (intensity - 30) / 70 * 3), 1, 4))


def filler_band(intensity):
    """강도별 filler 난이도 밴드: 'light' / 'all' / 'heavy'."""
    if intensity < 45:
        return "light"
    if intensity > 75:
        return "heavy"
    return "all"


def filler_load(f):
    return (f.get("load") or "light").lower()


def order_fillers(fillers, band):
    """밴드에 맞춰 filler 풀을 필터/정렬. light=가벼운 것만, heavy=무거운 것 우선."""
    if band == "light":
        out = [f for f in fillers if filler_load(f) == "light"]
        return out or list(fillers)  # light가 없으면 전체 폴백
    if band == "heavy":
        heavy = [f for f in fillers if filler_load(f) == "heavy"]
        light = [f for f in fillers if filler_load(f) != "heavy"]
        return heavy + light
    return list(fillers)


# ---- 시간 유틸 ----
def slot_abs_min(i):
    """슬롯 i의 시작 시각(기상 기준 절대 분, 자정 넘어가도 누적)."""
    return WAKE_MIN + 30 * i


def slot_clock(i):
    m = slot_abs_min(i) % (24 * 60)
    return m // 60, m % 60


def fmt(i):
    h, m = slot_clock(i)
    return f"{h:02d}:{m:02d}"


def slot_range(i):
    return f"{fmt(i)}–{fmt(i + 1)}"


def clock_to_slot(hhmm):
    """'HH:MM' -> 슬롯 인덱스 (10시 이전이면 다음날로 간주)."""
    h, m = map(int, hhmm.split(":"))
    cm = h * 60 + m
    if cm < WAKE_MIN:
        cm += 24 * 60
    return (cm - WAKE_MIN) // 30


def in_grad_window(i, win):
    s = clock_to_slot(win["start"])
    e = clock_to_slot(win["end"])
    return s <= i < e


def grad_allowed(i, win):
    """대학원 배치 가능: grad window 시작 ~ cutoff(22:00) 이전."""
    s = clock_to_slot(win["start"])
    c = clock_to_slot(win["cutoff"])
    return s <= i < c


# ---- 배치 헬퍼 ----
def find_contiguous(slots, n, prefer=None, allow=None):
    """비어있는 연속 n칸의 시작 인덱스. prefer 인덱스부터 우선 탐색.
    allow(i)가 주어지면 시작 i가 조건을 만족해야 함."""
    order = []
    if prefer is not None:
        order += list(range(prefer, N_SLOTS - n + 1))
    order += list(range(0, N_SLOTS - n + 1))
    for i in order:
        if allow and not all(allow(j) for j in range(i, i + n)):
            continue
        if all(slots[j] is None for j in range(i, i + n)):
            return i
    return None


def place(slots, i, label, typ, base=None):
    slots[i] = {"slot": i, "range": slot_range(i), "label": label,
                "type": typ, "base": base or label, "done": False}


def prev_base(slots, i):
    return slots[i - 1]["base"] if i > 0 and slots[i - 1] else None


# ---- 메인 ----
def generate(date_str, data, seed=0, base_slots=None, from_slot=0, carryover=None):
    """seed를 바꾸면 규칙은 그대로 둔 채 배치를 변형('다시 짜기').

    실시간 리플래닝: base_slots(기존 플랜 슬롯)와 from_slot을 주면
    slots[0..from_slot-1]을 그대로 잠그고 미래 슬롯만 재배치한다.
    carryover([{title, blocks, type}])는 잠근 직후 미래에 우선 배치."""
    cfg = data["config"]
    win = cfg["gradWindow"]
    not_grad_win = lambda i: not in_grad_window(i, win)
    intensity = intensity_for(data, date_str)
    try:
        weekday = _date.fromisoformat(date_str).weekday()  # 0=월 .. 6=일
    except (ValueError, TypeError):
        weekday = 0

    # 과거 슬롯 잠금 (리플래닝). 없으면 빈 하루.
    slots = [None] * N_SLOTS
    if base_slots and from_slot > 0:
        for i in range(min(from_slot, N_SLOTS)):
            if i < len(base_slots) and base_slots[i] is not None:
                slots[i] = dict(base_slots[i])

    # 0) 이월 항목 우선 배치 (미래 빈 슬롯에)
    for c in (carryover or []):
        n = max(1, int(c.get("blocks", 1)))
        typ = c.get("type", "goal")
        allow = None if typ == "grad" else not_grad_win
        start = find_contiguous(slots, n, allow=allow)
        if start is None and allow:  # 미래에 비-grad 자리가 없으면 제약 완화
            start = find_contiguous(slots, n)
        if start is not None:
            for k in range(n):
                place(slots, start + k, c.get("title", "이월"), typ,
                      base=c.get("base") or c.get("title", "이월"))

    # 1) 모닝 루틴 / 취침 준비 (잠긴 칸은 건드리지 않음)
    if slots[0] is None:
        place(slots, 0, "기상 · 모닝 루틴", "routine")
    if slots[N_SLOTS - 1] is None:
        place(slots, N_SLOTS - 1, "하루 마무리 · 취침 준비", "routine")

    # 2) 식사 (고정)
    for meal in cfg["fixedMeals"]:
        si = clock_to_slot(meal["start"])
        for k in range(meal["blocks"]):
            if 0 <= si + k < N_SLOTS and slots[si + k] is None:
                place(slots, si + k, meal["name"], "meal", base=meal["name"])

    # 3) 고정 일정(캘린더 대체) 🔒
    for ev in data.get("events", {}).get(date_str, []):
        s = clock_to_slot(ev["start"])
        e = clock_to_slot(ev["end"])
        for k in range(s, e):
            if 0 <= k < N_SLOTS and slots[k] is None:
                place(slots, k, f"[고정] {ev['title']} \U0001f512", "event",
                      base=ev["title"])

    goals = data.get("dailyGoals", {}).get(date_str, [])

    # 4) (중요) 최우선 — 어떤 규칙보다 먼저, 연속 배치 허용
    for g in goals:
        if g.get("important"):
            n = g.get("blocks", 1)
            start = find_contiguous(slots, n)
            if start is not None:
                for k in range(n):
                    place(slots, start + k, f"[중요] {g['title']}", "important",
                          base=g["title"])

    # 5) 운동 (연속 3블록, 대학원창 밖에만, seed로 시간대 변형) — 요일별 루틴 반영
    for h in data.get("habits", []):
        if h.get("contiguous") and habit_on_day(h, weekday):
            n = h["blocks"]
            base_pref = clock_to_slot(h["preferStart"]) if h.get("preferStart") else 14
            ex_cands = [base_pref, 20, 24, 12, 16]
            ex_cands = ex_cands[seed % len(ex_cands):] + ex_cands[:seed % len(ex_cands)]
            start = None
            for pref in ex_cands:
                start = find_contiguous(slots, n, prefer=pref, allow=not_grad_win)
                if start is not None:
                    break
            if start is None:
                start = find_contiguous(slots, n, allow=not_grad_win)
            if start is not None:
                for k in range(n):
                    place(slots, start + k, h["name"], "exercise", base=h["name"])

    # 5b) 자기계발 묶음 블록 (하루 3개를 한 번에, 대학원창 밖, 운동 후 선호)
    sd_cfg = cfg.get("selfDev")
    if sd_cfg:
        date_tasks = data.get("selfDev", {}).get(date_str)
        if date_tasks:
            picks = date_tasks[: sd_cfg.get("count", 3)]
        else:
            pool = sd_cfg.get("pool", [])
            cnt = sd_cfg.get("count", 3)
            if pool:
                digits = sum(int(c) for c in date_str if c.isdigit())
                off = (digits + seed) % len(pool)
                picks = [pool[(off + j) % len(pool)] for j in range(min(cnt, len(pool)))]
            else:
                picks = []
        if picks:
            n = sd_cfg.get("blocks", 1)
            pref = clock_to_slot(sd_cfg["preferStart"]) if sd_cfg.get("preferStart") else 20
            start = find_contiguous(slots, n, prefer=pref, allow=not_grad_win)
            if start is None:
                start = find_contiguous(slots, n, allow=not_grad_win)
            if start is not None:
                label = "자기계발: " + " · ".join(picks)
                for k in range(n):
                    place(slots, start + k, label, "selfdev", base="자기계발")

    # 6) 자유/여유 블록 미리 예약 (저녁~밤 선호, 대학원창 밖, seed로 변형)
    #    강도 설정 시 강도에 따라 블록 수 가감, 미설정 시 config 기본값.
    if intensity is not None:
        free_left = free_blocks_for(intensity)
    else:
        free_left = cfg.get("freeBlocksPerDay", 2)
    free_cands = [23, 28, 27, 29, 22, 26, 30, 31]
    free_cands = free_cands[seed % len(free_cands):] + free_cands[:seed % len(free_cands)]
    for cand in free_cands:
        if free_left <= 0:
            break
        if 0 <= cand < N_SLOTS and slots[cand] is None and not in_grad_window(cand, win):
            place(slots, cand, "자유 · 여유", "free")
            free_left -= 1

    # 7) 집중 시간대 세부 과업 풀 (프로젝트 번갈아)
    flabel = cfg.get("focusLabel") or "집중"
    grad = data.get("gradTasks", {})
    grad_units = []
    keys = list(grad.keys())
    lists = {k: list(grad[k].get("items", [])) for k in keys}
    idx = {k: 0 for k in keys}
    while any(idx[k] < len(lists[k]) for k in keys):
        for k in keys:
            if idx[k] < len(lists[k]):
                grad_units.append((k, lists[k][idx[k]]))
                idx[k] += 1
    gp = [seed]  # grad pointer (회차 반복, seed로 시작점 변형)

    def next_grad(prev):
        if not grad_units:
            return None
        for _ in range(len(grad_units)):
            k, item = grad_units[gp[0] % len(grad_units)]
            gp[0] += 1
            label = f"[{flabel}·{k}] {item}"
            if label != prev:
                return label, k
        return None

    # 7a) 대학원 전용 시간대(11~16) 빈 칸을 대학원으로 채움
    for i in range(N_SLOTS):
        if in_grad_window(i, win) and slots[i] is None:
            g = next_grad(prev_base(slots, i))
            if g:
                label, k = g
                place(slots, i, label, "grad", base=label)

    # 8) 나머지 채우기 (round-robin, 인터리빙)
    # 소스: 일반 데일리 목표, 독서매거진 습관, 대학원(22시 이전), filler
    goal_units = []
    for g in goals:
        if not g.get("important"):
            for _ in range(g.get("blocks", 1)):
                goal_units.append(("goal", f"[할일] {g['title']}", g["title"]))
    habit_units = []
    for h in data.get("habits", []):
        if (not h.get("contiguous") and (h.get("daily") or h.get("days"))
                and habit_on_day(h, weekday)):
            for _ in range(h["blocks"]):
                habit_units.append(("habit", f"[습관] {h['name']}", h["name"]))
    # 날짜별 맞춤 filler가 있으면 우선, 없으면 config 풀
    fillers = data.get("fillers", {}).get(date_str) or cfg.get("fillers", [])
    # 강도 설정 시 난이도 밴드로 filler 풀 필터/정렬
    if intensity is not None:
        fillers = order_fillers(fillers, filler_band(intensity))
    fp = [seed]

    def next_filler(prev):
        if not fillers:
            return None
        for _ in range(len(fillers) * 2):
            f = fillers[fp[0] % len(fillers)]
            fp[0] += 1
            base = f["name"]
            label = f"[filler] {base}"
            if base != prev:
                return label, base
        # 다른 게 없으면 그냥 첫 filler
        f = fillers[0]
        return f"[filler] {f['name']}", f["name"]

    def take_unit(pool, prev):
        # 직전과 다른 base만 꺼낸다 (연속 금지). 없으면 None -> 다음 소스로.
        for j, u in enumerate(pool):
            if u[2] != prev:
                return pool.pop(j)
        return None

    for i in range(N_SLOTS):
        if slots[i] is not None:
            continue
        prev = prev_base(slots, i)
        placed = False
        # 우선순위: 일반 목표 -> 습관 -> 대학원(가능시) -> filler
        u = take_unit(goal_units, prev)
        if u:
            place(slots, i, u[1], u[0], base=u[2]); placed = True
        if not placed:
            u = take_unit(habit_units, prev)
            if u:
                place(slots, i, u[1], u[0], base=u[2]); placed = True
        if not placed and grad_allowed(i, win):
            g = next_grad(prev)
            if g:
                place(slots, i, g[0], "grad", base=g[0]); placed = True
        if not placed:
            f = next_filler(prev)
            if f:
                place(slots, i, f[0], "filler", base=f[1]); placed = True
        if not placed:
            place(slots, i, "자유 · 여유", "free")

    return {"date": date_str, "slots": slots}


def to_markdown(plan):
    lines = [f"# \U0001f4c5 {plan['date']} 데일리 플랜", ""]
    for s in plan["slots"]:
        lines.append(f"{s['range']}  {s['label']}")
    return "\n".join(lines) + "\n"
