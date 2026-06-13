const $ = (s) => document.querySelector(s);

const TYPE_LABELS = {
  grad: "대학원", goal: "할일", filler: "filler", meal: "식사",
  exercise: "운동", free: "자유", event: "고정일정", important: "중요",
  routine: "루틴", selfdev: "자기계발",
};

function todayISO() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

let curDate = todayISO();
let replanSeed = 0;
let appConfig = {};
let lastHabits = [];

function focusLabel() {
  return appConfig.focusLabel || "집중";
}

async function refreshAll() {
  // plan + state를 한 번의 요청으로 (ngrok 왕복 최소화)
  const data = await api(`/api/bootstrap?date=${curDate}`);
  appConfig = data.config || {};
  renderPlan(data.plan);
  renderCondition(data.condition);
  renderHabits(data.habits || []);
  loadDateContext(data);
  loadUpcoming(data);
  if (data.setupNeeded) openSetupWizard(data);
}

// ---- 오늘 컨디션 → 강도 ----
const MOOD_EMOJI = ["😞", "😕", "😐", "🙂", "😄"];
const ENERGY_EMOJI = ["🪫", "😪", "🙂", "💪", "⚡"];
let condMood = null;
let condEnergy = null;

function clampN(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

function intensityPreview(mood, energy) {
  // scheduler.intensity_from 과 동일 공식 (미리보기용)
  const e = (clampN(energy, 1, 5) - 1) / 4;
  const m = (clampN(mood, 1, 5) - 1) / 4;
  return Math.round(clampN((e * 0.6 + m * 0.4) * 70 + 30, 30, 100));
}

function freeBlocksPreview(intensity) {
  return clampN(Math.round(4 - (intensity - 30) / 70 * 3), 1, 4);
}

function buildCondOpts(containerSel, emojis, getVal, setVal) {
  const box = $(containerSel);
  box.innerHTML = "";
  emojis.forEach((emo, idx) => {
    const v = idx + 1;
    const b = el("button", "cond-opt");
    b.textContent = emo;
    b.title = v + "단계";
    b.onclick = () => { setVal(v); paintCond(); };
    box.appendChild(b);
  });
}

function paintCond() {
  document.querySelectorAll("#moodOpts .cond-opt").forEach((b, i) =>
    b.classList.toggle("on", i + 1 === condMood));
  document.querySelectorAll("#energyOpts .cond-opt").forEach((b, i) =>
    b.classList.toggle("on", i + 1 === condEnergy));
  const ready = condMood && condEnergy;
  $("#condSave").disabled = !ready;
  if (ready) {
    const it = intensityPreview(condMood, condEnergy);
    $("#condPct").textContent = `오늘 강도 ${it}%`;
    $("#condHint").textContent = `여유 ${freeBlocksPreview(it)}블록 · 저장하면 플랜에 반영돼요`;
  } else {
    $("#condPct").textContent = "—";
  }
}

function renderCondition(c) {
  if (c) {
    condMood = c.mood || null;
    condEnergy = c.energy || null;
    const srcEl = $("#condSrc");
    if (c.source === "morning") {
      srcEl.textContent = "✅ 확정";
    } else if (c.source === "midnight") {
      srcEl.textContent = "🌙 자정 추정";
      srcEl.title = c.reason || "어제 활동 기반 추정값";
    } else {
      srcEl.textContent = "";
    }
  } else {
    condMood = null;
    condEnergy = null;
    $("#condSrc").textContent = "";
  }
  paintCond();
}

async function saveCondition() {
  if (!condMood || !condEnergy) return;
  const btn = $("#condSave");
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = "저장 중…";
  try {
    const r = await api("/api/condition", {
      method: "POST",
      body: JSON.stringify({ date: curDate, mood: condMood, energy: condEnergy }),
    });
    renderPlan(r.plan);
    renderCondition(r.condition);
  } catch (e) {
    alert("컨디션 저장 실패: " + e);
  } finally {
    btn.textContent = prev;
  }
}

function updateBadges() {
  const b1 = $("#goalDateBadge"), b2 = $("#evDateBadge");
  if (b1) b1.textContent = "→ " + curDate;
  if (b2) b2.textContent = "→ " + curDate;
}

async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({ "ngrok-skip-browser-warning": "true" }, opts.headers || {});
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    throw new Error("서버에 연결할 수 없어요. 연구실 PC의 플래너 서버가 꺼졌는지 확인하세요.");
  }
  if (r.status === 401) { location.href = "/"; return; }
  if (!r.ok) {
    if (r.status === 502 || r.status === 503 || r.status === 504) {
      throw new Error("서버가 응답하지 않아요(502). 연구실 PC에서 서버를 다시 켜주세요.");
    }
    throw new Error(`서버 오류 ${r.status}`);
  }
  const ct = r.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    throw new Error("서버 응답이 올바르지 않아요(서버가 재시작 중일 수 있음).");
  }
  return r.json();
}

function renderLegend() {
  const el = $("#legend");
  el.innerHTML = "";
  Object.entries(TYPE_LABELS).forEach(([t, name]) => {
    const s = document.createElement("span");
    s.className = "t-" + t;
    s.style.background = getComputedStyle(document.documentElement)
      .getPropertyValue("--" + t).trim() || "#555";
    s.textContent = t === "grad" ? focusLabel() : name;
    el.appendChild(s);
  });
}

function isGradWindow(range) {
  const h = parseInt(range.slice(0, 2), 10);
  const m = parseInt(range.slice(3, 5), 10);
  const t = h * 60 + m;
  return t >= 11 * 60 && t < 16 * 60;
}

let nowSlot = -1;

function nowHHMM() {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" +
         String(d.getMinutes()).padStart(2, "0");
}

function clockToSlot(hhmm) {
  // scheduler.clock_to_slot 과 동일 규칙 (10:00 기상 기준, 이전이면 다음날)
  const [h, m] = hhmm.split(":").map(Number);
  let cm = h * 60 + m;
  if (cm < 600) cm += 1440;
  return Math.floor((cm - 600) / 30);
}

// ---- U3: 달성률 띠 + 주간 streak (기존 done 체크 재사용, 신규 계산/라우트 0) ----
// 의미항목 = 루틴·식사·자유·filler 제외 (개인앱 달성률 산식과 동일)
const MEANINGFUL = new Set(["grad", "goal", "exercise", "important", "selfdev", "event"]);
function dayPct(slots) {
  const seen = new Set();
  let done = 0, total = 0;
  (slots || []).forEach((s) => {
    if (!MEANINGFUL.has(s.type)) return;
    const key = (s.base || s.label) + "|" + s.type;  // 같은 작업 여러 슬롯=1건
    if (seen.has(key)) return;
    seen.add(key);
    total += 1;
    if (s.done) done += 1;
  });
  return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
}

function renderPlan(plan) {
  $("#ttTitle").textContent = `${plan.date} 타임테이블`;
  nowSlot = plan.date === todayISO() ? clockToSlot(nowHHMM()) : -1;
  renderLegend();  // focusLabel(config)이 로드된 뒤 반영되도록 매 렌더 갱신
  const ol = $("#slots");
  ol.innerHTML = "";
  plan.slots.forEach((s) => ol.appendChild(buildSlotRow(plan.date, s)));
  lastPlan = plan;
  populateLeftPanel(plan);
  renderAchvBand(plan);
}

function renderAchvBand(plan) {
  const band = $("#achvBand");
  if (!band) return;
  const { done, total, pct } = dayPct(plan.slots);
  if (!total) { band.classList.add("hidden"); return; }
  band.classList.remove("hidden");
  $("#achvPct").textContent = pct + "%";
  $("#achvHint").textContent = `오늘 달성률 (${done}/${total})`;
  $("#achvFill").style.width = pct + "%";
  updateStreak().catch(() => {});  // 점은 실패해도 띠 본체는 유지
}

// 주간 streak: 이미 있는 /api/week 재사용 (라우트 추가 0)
async function updateStreak() {
  const dots = $("#streakDots");
  if (!dots) return;
  const data = await api(`/api/week?date=${curDate}`);
  const today = todayISO();
  dots.innerHTML = "";
  (data.days || []).forEach((d) => {
    const { pct, total } = dayPct(d.slots);
    const isToday = d.date === today;
    const future = d.date > today;
    let cls = "dot";
    if (future) cls += " future";
    else if (total && pct >= 60) cls += " hit";       // 그날 달성
    else if (total && pct > 0) cls += " partial";     // 부분 달성
    if (isToday) cls += " today";
    const dot = el("span", cls);
    dot.title = `${d.date.slice(5)} · ${future ? "예정" : pct + "%"}`;
    dots.appendChild(dot);
  });
}

// ---- 실시간 리플래닝 ----
const REPLAN_TYPES = new Set(["important", "goal", "grad", "selfdev", "exercise", "habit"]);

function gatherCarryCandidates(fromSlot) {
  if (!lastPlan) return [];
  const by = new Map();
  lastPlan.slots.forEach((s) => {
    if (s.slot >= fromSlot || s.done || !REPLAN_TYPES.has(s.type)) return;
    const key = s.base || s.label;
    if (!by.has(key)) by.set(key, { base: key, label: s.label, type: s.type, blocks: 0 });
    by.get(key).blocks += 1;
  });
  return [...by.values()];
}

async function sendReplan(carryover) {
  const r = await api("/api/replan", {
    method: "POST",
    body: JSON.stringify({ date: curDate, now: nowHHMM(), carryover }),
  });
  $("#carryPanel").classList.add("hidden");
  if (r.ended) {
    alert("오늘 일정이 이미 끝났어요 🌙");
    return;
  }
  renderPlan(r.plan);
}

function openReplanNow() {
  const fromSlot = clockToSlot(nowHHMM());
  if (curDate !== todayISO()) {
    alert("실시간 다시 짜기는 오늘 날짜에서만 동작해요.");
    return;
  }
  if (fromSlot >= 34) {
    alert("오늘 일정이 이미 끝났어요 🌙");
    return;
  }
  const cands = gatherCarryCandidates(fromSlot);
  if (!cands.length) {
    sendReplan([]);  // 이월할 게 없으면 바로 남은 시간 재배치
    return;
  }
  const panel = $("#carryPanel");
  panel.innerHTML = "";
  panel.classList.remove("hidden");
  const h = el("p", "carry-h");
  h.textContent = "아직 못 한 일 중 남은 시간에 다시 넣을 항목을 고르세요 (안 골라도 괜찮아요)";
  panel.appendChild(h);
  const list = el("div", "carry-list");
  cands.forEach((c, i) => {
    const lab = el("label", "carry-item");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.dataset.idx = i;
    const span = el("span");
    span.textContent = shortLabel(c.label) + (c.blocks > 1 ? ` (${c.blocks})` : "");
    lab.append(cb, span);
    list.appendChild(lab);
  });
  panel.appendChild(list);
  const actions = el("div", "carry-actions");
  const go = el("button");
  go.textContent = "다시 짜기";
  const cancel = el("button", "ghost");
  cancel.textContent = "취소";
  actions.append(go, cancel);
  panel.appendChild(actions);
  cancel.onclick = () => panel.classList.add("hidden");
  go.onclick = () => {
    const picked = [...list.querySelectorAll("input:checked")].map((cb) => {
      const c = cands[+cb.dataset.idx];
      return { title: c.label, blocks: c.blocks, type: c.type, base: c.base };
    });
    go.disabled = true;
    go.textContent = "재배치 중…";
    sendReplan(picked).finally(() => { go.disabled = false; go.textContent = "다시 짜기"; });
  };
}

async function loadPlan(date) {
  renderPlan(await api(`/api/plan?date=${date}`));
}

let lastPlan = null;

function currentSelfDev() {
  if (!lastPlan) return [];
  const s = lastPlan.slots.find((x) => x.type === "selfdev");
  return s ? s.label.replace(/^자기계발:\s*/, "").split(" · ")
    .map((t) => t.trim()).filter(Boolean) : [];
}

function currentUrgent() {
  if (!lastPlan) return [];
  const cnt = {}, order = [];
  lastPlan.slots.forEach((s) => {
    if (s.type === "important") {
      const t = s.label.replace(/^\[중요\]\s*/, "").trim();
      if (!(t in cnt)) { cnt[t] = 0; order.push(t); }
      cnt[t]++;
    }
  });
  return order.map((t) => (cnt[t] > 1 ? `${t} (${cnt[t]})` : t));
}

function openCardEditor(kind) {
  const isSd = kind === "sd";
  const listEl = $(isSd ? "#sdList" : "#urgentList");
  const card = listEl.closest(".card");
  if (card.querySelector(".cardeditor")) return;
  const items = isSd ? currentSelfDev() : currentUrgent();
  listEl.style.display = "none";
  const box = el("div", "cardeditor");
  const ta = el("textarea");
  ta.rows = 4;
  ta.value = items.join("\n");
  ta.placeholder = isSd ? "한 줄에 하나 (최대 3개)"
    : "한 줄에 하나 · '(n)'으로 블록 수 (예: 발표 준비 (2))";
  const hint = el("p", "hint");
  hint.textContent = isSd ? "자기계발 3가지 직접 입력" : "긴급 일 (최대 5개)";
  const actions = el("div", "ed-actions");
  const save = el("button"); save.textContent = "저장";
  const cancel = el("button", "ghost"); cancel.textContent = "취소";
  actions.append(save, cancel);
  box.append(ta, hint, actions);
  card.appendChild(box);
  ta.focus();
  cancel.onclick = () => { box.remove(); listEl.style.display = ""; };
  save.onclick = async () => {
    const lines = ta.value.split("\n").map((l) => l.trim()).filter(Boolean);
    if (isSd) {
      await api("/api/self-dev", { method: "POST",
        body: JSON.stringify({ date: curDate, tasks: lines.slice(0, 3) }) });
    } else {
      const its = lines.slice(0, 5).map((l) => {
        const m = l.match(/\((\d+)\)/);
        return { title: l.replace(/\(\d+\)/, "").trim(), blocks: m ? parseInt(m[1], 10) : 1 };
      });
      await api("/api/urgent", { method: "POST",
        body: JSON.stringify({ date: curDate, items: its }) });
    }
    loadPlan(curDate);
  };
}

// ---- 평소 루틴 편집 ----
function habitRow(h) {
  h = h || { name: "", blocks: 1, contiguous: false, preferStart: "" };
  const row = el("div", "habit-row");
  const name = el("input", "h-name");
  name.placeholder = "루틴 이름 (예: 운동)";
  name.value = h.name || "";
  const blocks = el("input", "h-blocks");
  blocks.type = "number"; blocks.min = 1; blocks.max = 8;
  blocks.value = h.blocks || 1; blocks.title = "30분 칸 수";
  const contWrap = el("label", "h-cont");
  const cont = el("input"); cont.type = "checkbox"; cont.checked = !!h.contiguous;
  contWrap.append(cont, document.createTextNode("연속"));
  const pref = el("input", "h-pref");
  pref.type = "time"; pref.value = h.preferStart || ""; pref.disabled = !cont.checked;
  pref.title = "선호 시작시각 (연속일 때만)";
  cont.onchange = () => { pref.disabled = !cont.checked; };
  const del = el("button", "del"); del.textContent = "삭제";
  del.onclick = () => row.remove();
  row.append(name, blocks, contWrap, pref, del);
  return row;
}

function renderHabits(habits) {
  lastHabits = habits || [];
  const box = $("#habitRows");
  if (!box) return;
  box.innerHTML = "";
  lastHabits.forEach((h) => box.appendChild(habitRow(h)));
}

function collectHabits(container) {
  return [...container.querySelectorAll(".habit-row")].map((r) => {
    const ps = r.querySelector(".h-pref").value;
    return {
      name: r.querySelector(".h-name").value.trim(),
      blocks: parseInt(r.querySelector(".h-blocks").value, 10) || 1,
      contiguous: r.querySelector(".h-cont input").checked,
      preferStart: ps || undefined,
    };
  }).filter((h) => h.name);
}

async function saveHabits() {
  const habits = collectHabits($("#habitRows"));
  await api("/api/habits", { method: "POST", body: JSON.stringify({ habits }) });
  await api("/api/generate", { method: "POST", body: JSON.stringify({ date: curDate, seed: 0 }) });
  refreshAll();
}

// ---- 초기 세팅 위저드 ----
function suField(labelText, ...controls) {
  const d = el("div", "setup-field");
  const l = el("label", "setup-q"); l.textContent = labelText;
  d.appendChild(l);
  const c = el("div", "setup-controls");
  controls.forEach((x) => c.appendChild(x));
  d.appendChild(c);
  return d;
}

function mealRow(m) {
  m = m || { name: "식사", start: "12:00", blocks: 1 };
  const row = el("div", "habit-row");
  const name = el("input", "m-name"); name.value = m.name; name.placeholder = "이름";
  const start = el("input", "m-start"); start.type = "time"; start.value = m.start;
  const blocks = el("input", "m-blocks"); blocks.type = "number"; blocks.min = 1; blocks.max = 4;
  blocks.value = m.blocks || 1; blocks.title = "30분 칸 수";
  const del = el("button", "del"); del.textContent = "삭제"; del.onclick = () => row.remove();
  row.append(name, start, blocks, del);
  return row;
}

function fillerRow(f) {
  f = f || { name: "", load: "light" };
  const row = el("div", "habit-row");
  const name = el("input", "f-name"); name.value = f.name; name.placeholder = "빈 시간에 할 활동";
  const load = el("select", "f-load");
  [["light", "가벼움"], ["heavy", "무거움"]].forEach(([v, t]) => {
    const o = el("option"); o.value = v; o.textContent = t;
    if ((f.load || "light") === v) o.selected = true;
    load.appendChild(o);
  });
  const del = el("button", "del"); del.textContent = "삭제"; del.onclick = () => row.remove();
  row.append(name, load, del);
  return row;
}

function openSetupWizard(data) {
  const cfg = (data && data.config) || appConfig || {};
  const habits = (data && data.habits) || lastHabits || [];
  const gw = cfg.gradWindow || { start: "11:00", end: "16:00", cutoff: "22:00" };
  const sd = cfg.selfDev || { pool: [], count: 3, preferStart: "20:00" };
  const form = $("#setupForm");
  form.innerHTML = "";
  const num = (id, val, min, max) => {
    const i = el("input"); i.type = "number"; i.id = id; i.value = val;
    i.min = min; i.max = max; return i;
  };
  const time = (id, val) => { const i = el("input"); i.type = "time"; i.id = id; i.value = val || ""; return i; };
  const text = (id, val, ph) => { const i = el("input"); i.id = id; i.value = val || ""; i.placeholder = ph || ""; return i; };

  form.appendChild(suField("1. 보통 몇 시에 일어나요?", time("suWake", cfg.wake || "10:00")));
  form.appendChild(suField("2. 몇 시에 자요?", time("suSleep", cfg.sleep || "03:00")));
  form.appendChild(suField("3. 가장 몰입하는 '집중 시간대' 이름과 시간대",
    text("suFocusName", cfg.focusLabel || "집중", "이름 (예: 대학원/업무/공부)"),
    time("suFocusStart", gw.start), time("suFocusEnd", gw.end)));
  form.appendChild(suField("4. 그 집중 작업은 몇 시 이후엔 안 해요? (마감)", time("suCutoff", gw.cutoff)));

  const meals = el("div", "su-sub"); meals.id = "suMealRows";
  (cfg.fixedMeals || [{ name: "아침 식사", start: "10:30", blocks: 1 },
    { name: "점심 식사", start: "12:00", blocks: 2 },
    { name: "저녁 식사", start: "19:00", blocks: 2 }]).forEach((m) => meals.appendChild(mealRow(m)));
  const addMeal = el("button", "ghost"); addMeal.textContent = "+ 식사 추가";
  addMeal.onclick = () => meals.appendChild(mealRow());
  form.appendChild(suField("5. 식사 시각 (이름·시각·30분칸 수)", meals, addMeal));

  const hrows = el("div", "su-sub"); hrows.id = "suHabitRows";
  habits.forEach((h) => hrows.appendChild(habitRow(h)));
  const addHabit = el("button", "ghost"); addHabit.textContent = "+ 루틴 추가";
  addHabit.onclick = () => hrows.appendChild(habitRow());
  form.appendChild(suField("6. 매일 하는 운동·루틴 (연속·선호시각)", hrows, addHabit));

  const pool = el("textarea"); pool.id = "suSelfPool"; pool.rows = 4;
  pool.value = (sd.pool || []).join("\n");
  pool.placeholder = "한 줄에 하나 (예: 5분 저널, 영어단어 5개)";
  form.appendChild(suField("7. 매일 챙길 자기계발 항목들", pool, num("suSelfCount", sd.count || 3, 1, 5)));

  const frows = el("div", "su-sub"); frows.id = "suFillerRows";
  (cfg.fillers || []).forEach((f) => frows.appendChild(fillerRow(f)));
  if (!(cfg.fillers || []).length) frows.appendChild(fillerRow());
  const addFiller = el("button", "ghost"); addFiller.textContent = "+ 활동 추가";
  addFiller.onclick = () => frows.appendChild(fillerRow());
  form.appendChild(suField("8. 빈 시간에 채울 활동(filler)과 난이도", frows, addFiller));

  form.appendChild(suField("9. 하루 자유·여유 시간 (30분 블록 수)", num("suFree", cfg.freeBlocksPerDay ?? 2, 0, 8)));
  form.appendChild(suField("10. 자기계발을 주로 몇 시쯤 묶어서 할래요?", time("suSelfPref", sd.preferStart || "20:00")));

  $("#setupOverlay").classList.remove("hidden");
}

function collectSetup() {
  const meals = [...$("#suMealRows").querySelectorAll(".habit-row")].map((r) => ({
    name: r.querySelector(".m-name").value.trim() || "식사",
    start: r.querySelector(".m-start").value || "12:00",
    blocks: parseInt(r.querySelector(".m-blocks").value, 10) || 1,
  })).filter((m) => m.start);
  const fillers = [...$("#suFillerRows").querySelectorAll(".habit-row")].map((r) => ({
    name: r.querySelector(".f-name").value.trim(),
    load: r.querySelector(".f-load").value,
    blocks: 1,
  })).filter((f) => f.name);
  const pool = $("#suSelfPool").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const config = {
    wake: $("#suWake").value || "10:00",
    sleep: $("#suSleep").value || "03:00",
    focusLabel: $("#suFocusName").value.trim() || "집중",
    gradWindow: {
      start: $("#suFocusStart").value || "11:00",
      end: $("#suFocusEnd").value || "16:00",
      cutoff: $("#suCutoff").value || "22:00",
    },
    fixedMeals: meals,
    fillers,
    freeBlocksPerDay: parseInt($("#suFree").value, 10) || 0,
    selfDev: {
      pool,
      count: parseInt($("#suSelfCount").value, 10) || 3,
      blocks: 1,
      preferStart: $("#suSelfPref").value || "20:00",
    },
  };
  const habits = collectHabits($("#suHabitRows"));
  return { config, habits };
}

async function saveSetup() {
  const btn = $("#setupSave");
  btn.disabled = true; const prev = btn.textContent; btn.textContent = "저장 중…";
  try {
    const { config, habits } = collectSetup();
    const r = await api("/api/setup", {
      method: "POST",
      body: JSON.stringify({ date: curDate, config, habits }),
    });
    appConfig = r.config || appConfig;
    $("#setupOverlay").classList.add("hidden");
    refreshAll();
  } catch (e) {
    alert("세팅 저장 실패: " + e);
  } finally {
    btn.disabled = false; btn.textContent = prev;
  }
}

const QUOTES = [
  { t: "오늘 할 수 있는 일에 전력을 다하라. 그러면 내일은 한 걸음 더 나아가 있을 것이다.", a: "아이작 뉴턴" },
  { t: "지금 잠을 자면 꿈을 꾸지만, 지금 공부하면 꿈을 이룬다.", a: "하버드 도서관" },
  { t: "성공은 매일 반복한 작은 노력들의 합이다.", a: "로버트 콜리어" },
  { t: "시작하는 방법은 그만 말하고 행동하는 것이다.", a: "월트 디즈니" },
  { t: "할 수 있다고 믿는 사람은 결국 그렇게 된다.", a: "샤를 드골" },
  { t: "오늘 누군가 그늘에 앉아 쉴 수 있는 건 오래전 누군가 나무를 심었기 때문이다.", a: "워런 버핏" },
  { t: "느리게 가는 것을 두려워 말고, 멈춰 서는 것을 두려워하라.", a: "중국 속담" },
  { t: "위대한 일은 작은 일들이 모여 이루어진다.", a: "빈센트 반 고흐" },
  { t: "지식에 대한 투자가 항상 최고의 이자를 지급한다.", a: "벤저민 프랭클린" },
  { t: "행동은 모든 성공의 기초가 되는 열쇠다.", a: "파블로 피카소" },
  { t: "어제보다 나은 오늘, 그것이 전부다.", a: "작자 미상" },
  { t: "집중이란 '아니오'라고 말하는 것이다.", a: "스티브 잡스" },
  { t: "완벽을 두려워하지 마라. 어차피 도달하지 못한다.", a: "살바도르 달리" },
  { t: "포기하지 않는 한 실패는 없다.", a: "토머스 에디슨" },
  { t: "가장 큰 위험은 위험 없는 삶이다.", a: "스티븐 코비" },
  { t: "꾸준함은 재능을 이긴다.", a: "작자 미상" },
];
function randomQuote() {
  return QUOTES[Math.floor(Math.random() * QUOTES.length)];
}

function renderMini(listSel, cntSel, items, emptyText) {
  const ul = $(listSel);
  ul.innerHTML = "";
  $(cntSel).textContent = items.length;
  if (!items.length) {
    const li = el("li", "empty");
    li.textContent = emptyText;
    ul.appendChild(li);
    return;
  }
  items.forEach((t) => {
    const li = el("li");
    const span = el("span");
    span.textContent = t;
    li.appendChild(span);
    ul.appendChild(li);
  });
}

function populateLeftPanel(plan) {
  const sdSlot = plan.slots.find((s) => s.type === "selfdev");
  let sd = [];
  if (sdSlot) {
    sd = sdSlot.label.replace(/^자기계발:\s*/, "").split(" · ")
      .map((x) => x.trim()).filter(Boolean);
  }
  renderMini("#sdList", "#sdCnt", sd.slice(0, 3), "오늘 자기계발 항목 없음");

  const seen = new Set();
  const urgent = [];
  plan.slots.forEach((s) => {
    if (s.type === "important") {
      const t = s.label.replace(/^\[중요\]\s*/, "").trim();
      if (!seen.has(t)) { seen.add(t); urgent.push(t); }
    }
  });
  renderMini("#urgentList", "#urgentCnt", urgent.slice(0, 5), "긴급 항목 없음");
}

function buildSlotRow(date, s) {
  const li = el("li", "slot t-" + s.type + (s.done ? " done" : "") +
    (isGradWindow(s.range) ? " gradwin" : "") + (s.edited ? " edited" : "") +
    (s.slot === nowSlot ? " now" : ""));
  const cb = el("input");
  cb.type = "checkbox";
  cb.checked = !!s.done;
  cb.onchange = () => api("/api/done", {
    method: "POST", body: JSON.stringify({ date, slot: s.slot, done: cb.checked }),
  }).then((j) => {
    li.classList.toggle("done", cb.checked);
    handleDoneResponse(j, cb.checked);
  });
  const time = el("span", "time");
  time.textContent = s.range;
  const body = el("div", "slotbody");
  const label = el("span", "label");
  label.textContent = s.label;
  body.appendChild(label);
  if (s.note) {
    const note = el("div", "note");
    note.textContent = s.note;
    body.appendChild(note);
  }
  body.onclick = () => openSlotEditor(li, date, s);
  const editBtn = el("button", "editbtn");
  editBtn.textContent = "✎";
  editBtn.title = "이 시간 직접 수정 / 메모";
  editBtn.onclick = () => openSlotEditor(li, date, s);
  li.append(cb, time, body, editBtn);
  return li;
}

function openSlotEditor(li, date, s) {
  li.className = "slot editing t-" + s.type;
  li.innerHTML = "";
  const time = el("span", "time");
  time.textContent = s.range;
  const box = el("div", "editbox");
  const lin = el("input", "ed-label");
  lin.value = s.label;
  lin.placeholder = "이 시간에 할 일";
  const nin = el("textarea", "ed-note");
  nin.value = s.note || "";
  nin.placeholder = "세부 메모 (여러 줄 가능, 내가 직접 적는 내용)";
  nin.rows = 2;
  const actions = el("div", "ed-actions");
  const save = el("button");
  save.textContent = "저장";
  const reset = el("button", "ghost");
  reset.textContent = "되돌리기";
  const cancel = el("button", "ghost");
  cancel.textContent = "취소";
  actions.append(save, reset, cancel);
  box.append(lin, nin, actions);
  li.append(time, box);
  lin.focus();
  const send = (payload) => api("/api/slot", {
    method: "POST", body: JSON.stringify(payload),
  }).then(() => loadPlan(date));
  save.onclick = () => send({ date, slot: s.slot, label: lin.value, note: nin.value });
  reset.onclick = () => send({ date, slot: s.slot, reset: true });
  cancel.onclick = () => loadPlan(date);
  lin.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); save.click(); }
  });
}

async function loadDateContext(st) {
  st = st || await api("/api/state");
  // 선택 날짜의 데일리 목표를 입력칸에 채워 수정/삭제 쉽게
  const goals = (st.dailyGoals || {})[curDate] || [];
  $("#goalInput").value = goals.map((g) =>
    `${g.title}${g.blocks > 1 ? ` (${g.blocks})` : " (1)"}${g.important ? "(중요)" : ""}`
  ).join("\n");
  // 선택 날짜의 고정 일정 목록 + 삭제 버튼
  const evs = (st.events || {})[curDate] || [];
  const ul = $("#evList");
  ul.innerHTML = evs.length ? "" : '<li class="muted">등록된 약속 없음</li>';
  evs.forEach((e, i) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = `${e.start}–${e.end} ${e.title}`;
    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "삭제";
    del.onclick = async () => {
      await api("/api/events/delete", {
        method: "POST",
        body: JSON.stringify({ date: curDate, index: i }),
      });
      // 일정이 사라졌으니 그 자리를 다시 채워 재생성
      await api("/api/generate", { method: "POST", body: JSON.stringify({ date: curDate }) });
      refreshAll();
    };
    li.append(span, del);
    ul.appendChild(li);
  });
}

async function loadUpcoming(st) {
  st = st || await api("/api/state");
  const today = todayISO();
  const items = [];
  Object.entries(st.dailyGoals || {}).forEach(([d, gs]) => {
    if (d >= today) gs.forEach((g, i) =>
      items.push({ d, i, kind: "goal",
        text: `${d} · ${g.title}${g.important ? " (중요)" : ""}` }));
  });
  Object.entries(st.events || {}).forEach(([d, evs]) => {
    if (d >= today) evs.forEach((e, i) =>
      items.push({ d, i, kind: "event", text: `${d} · ${e.start} ${e.title} 🔒` }));
  });
  items.sort((a, b) => a.text.localeCompare(b.text));
  const ul = $("#upcoming");
  ul.innerHTML = items.length ? "" : "<li class='muted'>예약된 항목 없음</li>";
  items.forEach((it) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = it.text;
    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "삭제";
    del.onclick = async () => {
      const path = it.kind === "goal" ? "/api/daily-goals/delete" : "/api/events/delete";
      await api(path, { method: "POST", body: JSON.stringify({ date: it.d, index: it.i }) });
      // 이미 생성된 플랜이면 그 날짜 재생성
      await api("/api/generate", { method: "POST", body: JSON.stringify({ date: it.d, seed: 0 }) });
      refreshAll();
    };
    li.append(span, del);
    ul.appendChild(li);
  });
  // 향후계획 갱신 경고
  const warn = $("#warn");
  const month = today.slice(0, 7);
  const stale = Object.values(st.gradTasks || {}).some(
    (g) => (g.extractedAt || "").slice(0, 7) !== month);
  if (stale) {
    warn.classList.remove("hidden");
    warn.textContent = "⚠️ 대학원 향후계획 캐시가 이번 달 것이 아닙니다. [이번 달 향후계획 갱신]을 눌러주세요.";
  } else {
    warn.classList.add("hidden");
  }
}

function parseGoals(text) {
  return text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const important = /\(중요\)/.test(l);
    const bm = l.match(/\((\d+)\)/);
    const blocks = bm ? parseInt(bm[1], 10) : 1;
    const title = l.replace(/\(중요\)/g, "").replace(/\(\d+\)/g, "").trim();
    return { title, blocks, important };
  });
}

const chatHistory = [];

function appendChat(role, text) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function sendChat() {
  const inp = $("#chatInput");
  const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
  appendChat("user", text);
  chatHistory.push({ role: "user", content: text });
  const thinking = appendChat("assistant", "…");
  $("#chatSend").disabled = true;
  try {
    const r = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ history: chatHistory, date: curDate }),
    });
    thinking.textContent = r.reply || "(빈 응답)";
    chatHistory.push({ role: "assistant", content: r.reply || "" });
    if (r.changed) refreshAll();
  } catch (e) {
    thinking.textContent = "오류: " + e;
  } finally {
    $("#chatSend").disabled = false;
  }
}

let weekAnchor = todayISO();

function shortLabel(label) {
  let s = label.replace("\u{1F512}", "").trim();
  s = s.replace(/^\[[^·\]]+·[^\]]*\]\s*/, "")
       .replace(/^\[(할일|습관|filler|중요|고정|캘린더)\]\s*/, "")
       .replace(/^자기계발:\s*/, "자기계발 ");
  return s;
}

function shiftDate(iso, days) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function fmtHour(hhmm) {
  let h = parseInt(hhmm.slice(0, 2), 10);
  const ap = h < 12 ? "AM" : "PM";
  let hh = h % 12;
  if (hh === 0) hh = 12;
  return hh + ap;
}

function gotoDaily(date) {
  curDate = date;
  $("#datePicker").value = date;
  updateBadges();
  showDaily();
  if (document.body.classList.contains("tab-week")) setMobileTab("today");
  refreshAll();
}

async function renderWeek() {
  const data = await api(`/api/week?date=${weekAnchor}`);
  const days = data.days;
  $("#weekTitle").textContent = `${days[0].date} ~ ${days[6].date}`;
  const grid = $("#weekGrid");
  grid.innerHTML = "";
  const n = days[0].slots.length;
  const ROW = 24;
  grid.style.gridTemplateColumns = `48px repeat(7, 1fr)`;
  grid.style.gridTemplateRows = `46px repeat(${n}, ${ROW}px)`;

  grid.appendChild(el("div", "wk-corner"));
  days.forEach((d, i) => {
    const h = el("div", "wk-dayhead" + (d.date === todayISO() ? " today" : ""));
    h.style.gridArea = `1 / ${i + 2}`;
    h.innerHTML = `<span>${d.dow}</span><b>${d.date.slice(8)}</b>`;
    h.title = `${d.date} 일간 보기`;
    h.onclick = () => gotoDaily(d.date);
    grid.appendChild(h);
  });
  // 세로 구분선
  for (let i = 0; i < 7; i++) {
    const c = el("div", "wk-colbg");
    c.style.gridArea = `2 / ${i + 2} / ${n + 2} / ${i + 3}`;
    grid.appendChild(c);
  }
  // 시간선 + 정시 라벨
  for (let r = 0; r < n; r++) {
    const start = days[0].slots[r].range.split("–")[0];
    if (start.slice(3) === "00") {
      const line = el("div", "wk-hourline");
      line.style.gridArea = `${r + 2} / 1 / ${r + 3} / -1`;
      grid.appendChild(line);
      const t = el("div", "wk-time");
      t.textContent = fmtHour(start);
      t.style.gridArea = `${r + 2} / 1`;
      grid.appendChild(t);
    }
  }
  // 이벤트: 연속 동일 라벨 병합
  days.forEach((d, i) => {
    let r = 0;
    while (r < n) {
      const s = d.slots[r];
      let len = 1;
      while (r + len < n && d.slots[r + len].label === s.label &&
             d.slots[r + len].type === s.type) len++;
      const endR = d.slots[r + len - 1].range.split("–")[1];
      const startR = s.range.split("–")[0];
      const ev = el("div", "wk-event ev-" + s.type + (s.done ? " done" : ""));
      ev.style.gridArea = `${r + 2} / ${i + 2} / span ${len} / span 1`;
      ev.title = `${d.date} ${startR}–${endR}\n${s.label}`;
      const tt = el("span", "t");
      tt.textContent = shortLabel(s.label);
      ev.appendChild(tt);
      if (len >= 2) {
        const rr = el("span", "r");
        rr.textContent = `${startR}–${endR}`;
        ev.appendChild(rr);
      }
      ev.onclick = () => gotoDaily(d.date);
      grid.appendChild(ev);
      r += len;
    }
  });
}

function showWeek() {
  $("#mainGrid").classList.add("hidden");
  $("#weekView").classList.remove("hidden");
  $("#btnWeek").classList.add("active");
  $("#btnDaily").classList.remove("active");
  renderWeek();
}

function showDaily() {
  $("#weekView").classList.add("hidden");
  $("#mainGrid").classList.remove("hidden");
  $("#btnDaily").classList.add("active");
  $("#btnWeek").classList.remove("active");
}

function setMobileTab(tab) {
  document.body.classList.remove("tab-today", "tab-week", "tab-tools");
  document.body.classList.add("tab-" + tab);
  document.querySelectorAll("#bnav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab));
  if (tab === "week") { weekAnchor = curDate; renderWeek(); }
  if (tab === "tools") loadCredits();
  window.scrollTo(0, 0);
}

// U2: Pro 티저 — '알림 받기' 대기리스트(프런트 전용, 라우트 무변경, 결제어 0).
// 가입 시 받은 이메일 재사용 → 추가 개인정보 수집 없음(R3').
function setupProTeaser() {
  const btn = $("#btnPro");
  const note = $("#proNote");
  if (!btn) return;
  const KEY = "proWaitlist";
  const joined = () => {
    btn.textContent = "✓ 출시되면 알려드릴게요";
    btn.classList.add("ghost");
    btn.disabled = true;
    if (note) note.textContent = "대기리스트에 등록됐어요. 출시되면 가입 이메일로 안내드릴게요.";
  };
  try { if (localStorage.getItem(KEY)) joined(); } catch (e) {}
  btn.onclick = () => {
    try { localStorage.setItem(KEY, "1"); } catch (e) {}
    joined();
  };
}

// ---- 크레딧 보상 ----
let creditState = null;
let shopEditMode = false;

async function loadCredits() {
  try { renderCredits(await api("/api/credits")); } catch (e) {}
}

function renderCredits(s) {
  if (!s) return;
  creditState = s;
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set("#cBalance", s.balance);
  set("#cEarned", s.earned);
  set("#cStreak", s.streak);
  const list = $("#shopList");
  if (!list) return;
  list.innerHTML = "";
  s.shop.forEach((it) => {
    const row = el("div", "shop-item");
    const name = el("span", "shop-name");
    name.textContent = `${it.emoji} ${it.name}`;
    row.appendChild(name);
    if (shopEditMode) {
      const del = el("button", "shop-del");
      del.textContent = "✕";
      del.title = "삭제";
      del.onclick = () => deleteShopItem(it.id);
      const price = el("span", "shop-price");
      price.textContent = `${it.price}`;
      row.appendChild(price);
      row.appendChild(del);
    } else {
      const buy = el("button", "buy");
      buy.textContent = `${it.price}`;
      buy.disabled = s.balance < it.price;
      buy.onclick = () => buyReward(it.id, it.name);
      row.appendChild(buy);
    }
    list.appendChild(row);
  });
}

async function buyReward(id, name) {
  const r = await api("/api/credits/buy", {
    method: "POST", body: JSON.stringify({ itemId: id }),
  });
  if (r && r.ok) { toast(`'${name}' 보상 구매! 🎉`); loadCredits(); }
  else { toast((r && r.error) || "크레딧이 부족해요"); }
}

function toggleShopEdit() {
  shopEditMode = !shopEditMode;
  const btn = $("#shopEditBtn");
  if (btn) btn.textContent = shopEditMode ? "완료" : "편집";
  const addRow = $("#shopAddRow");
  if (addRow) addRow.classList.toggle("hidden", !shopEditMode);
  renderCredits(creditState);
}

async function saveShop(shop) {
  const r = await api("/api/credits/shop", {
    method: "POST", body: JSON.stringify({ shop }),
  });
  if (r && r.shop) { creditState.shop = r.shop; loadCredits(); }
}

function addShopItem() {
  const name = ($("#shopName").value || "").trim();
  const price = parseInt($("#shopPrice").value, 10);
  if (!name || isNaN(price)) { toast("이름과 가격을 입력하세요"); return; }
  const shop = (creditState.shop || []).concat([{ name, price, emoji: "🎁", cat: "기타" }]);
  $("#shopName").value = ""; $("#shopPrice").value = "";
  saveShop(shop);
}

function deleteShopItem(id) {
  const shop = (creditState.shop || []).filter((i) => i.id !== id);
  saveShop(shop);
}

function handleDoneResponse(j, checked) {
  if (!j) return;
  if (j.credits) renderCredits(j.credits);
  if (checked) coinPop("+10");
  if (j.celebrate) {
    const key = `celebrated:${todayISO()}:${j.celebrate}`;
    let already = false;
    try { already = !!localStorage.getItem(key); } catch (e) {}
    if (!already) {
      try { localStorage.setItem(key, "1"); } catch (e) {}
      showCelebrate("100% 달성! 🔥", "오늘 플랜을 완벽하게 지켰어요!");
    }
  }
}

function showCelebrate(title, sub) {
  const box = $("#celebrate");
  if (!box) return;
  $("#celebrateTitle").textContent = title;
  $("#celebrateSub").textContent = sub;
  box.classList.remove("hidden");
  runConfetti();
}

function coinPop(text) {
  const p = el("div", "coin-pop");
  p.textContent = text;
  document.body.appendChild(p);
  setTimeout(() => p.remove(), 1100);
}

function runConfetti() {
  const cv = $("#confetti");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  cv.width = window.innerWidth;
  cv.height = window.innerHeight;
  const cols = ["#ffd166", "#ef476f", "#06d6a0", "#118ab2", "#8a5cf6"];
  const ps = Array.from({ length: 120 }, () => ({
    x: Math.random() * cv.width, y: -20 - Math.random() * cv.height,
    r: 4 + Math.random() * 5, c: cols[(Math.random() * cols.length) | 0],
    vy: 2 + Math.random() * 3, vx: -1 + Math.random() * 2,
  }));
  let frames = 0;
  (function tick() {
    frames++;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ps.forEach((p) => { p.y += p.vy; p.x += p.vx; ctx.fillStyle = p.c; ctx.fillRect(p.x, p.y, p.r, p.r); });
    if (frames < 160 && !$("#celebrate").classList.contains("hidden")) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, cv.width, cv.height);
  })();
}

let _toastTimer = null;
function toast(msg) {
  let t = $("#toast");
  if (!t) {
    t = el("div", "toast");
    t.id = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("show"), 2400);
}

function init() {
  renderLegend();
  document.body.classList.add("tab-today");
  document.querySelectorAll("#bnav button").forEach((b) =>
    (b.onclick = () => setMobileTab(b.dataset.tab)));
  $("#datePicker").value = curDate;
  updateBadges();
  $("#datePicker").onchange = (e) => {
    curDate = e.target.value;
    replanSeed = 0;
    updateBadges();
    refreshAll();
  };
  $("#btnReplan").onclick = async () => {
    replanSeed += 1;
    await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ date: curDate, seed: replanSeed }),
    });
    loadPlan(curDate);
  };
  $("#btnPng").onclick = () => {
    window.open(`/api/plan.png?date=${curDate}`, "_blank");
  };
  $("#btnRefresh").onclick = async () => {
    $("#btnRefresh").textContent = "갱신 중…";
    const r = await api("/api/refresh-grad", { method: "POST", body: "{}" });
    $("#btnRefresh").textContent = "이번 달 향후계획 갱신";
    alert(r.ok ? "향후계획 갱신 완료" : "갱신 실패: " + (r.error || ""));
    loadUpcoming();
  };
  $("#btnSaveGoals").onclick = async () => {
    const goals = parseGoals($("#goalInput").value);
    await api("/api/daily-goals", {
      method: "POST",
      body: JSON.stringify({ date: curDate, goals }),
    });
    replanSeed = 0;
    await api("/api/generate", { method: "POST", body: JSON.stringify({ date: curDate, seed: 0 }) });
    refreshAll();
  };
  $("#btnDaily").onclick = showDaily;
  $("#btnWeek").onclick = () => { weekAnchor = curDate; showWeek(); };
  $("#weekPrev").onclick = () => { weekAnchor = shiftDate(weekAnchor, -7); renderWeek(); };
  $("#weekNext").onclick = () => { weekAnchor = shiftDate(weekAnchor, 7); renderWeek(); };
  $("#weekToday").onclick = () => { weekAnchor = todayISO(); renderWeek(); };
  $("#weekPng").onclick = () => window.open(`/api/week.png?date=${weekAnchor}`, "_blank");
  buildCondOpts("#moodOpts", MOOD_EMOJI, () => condMood, (v) => { condMood = v; });
  buildCondOpts("#energyOpts", ENERGY_EMOJI, () => condEnergy, (v) => { condEnergy = v; });
  $("#condSave").onclick = saveCondition;
  $("#btnReplanNow").onclick = openReplanNow;
  $("#btnAddHabit").onclick = () => $("#habitRows").appendChild(habitRow());
  $("#btnSaveHabits").onclick = saveHabits;
  $("#btnSetup").onclick = () => openSetupWizard();
  setupProTeaser();
  if ($("#shopEditBtn")) $("#shopEditBtn").onclick = toggleShopEdit;
  if ($("#shopAddBtn")) $("#shopAddBtn").onclick = addShopItem;
  if ($("#celebrateClose")) $("#celebrateClose").onclick = () => $("#celebrate").classList.add("hidden");
  loadCredits();
  $("#btnLogout").onclick = async () => {
    try { await api("/api/logout", { method: "POST", body: "{}" }); } catch (e) {}
    location.href = "/";
  };
  $("#btnDeleteAccount").onclick = async () => {
    if (!confirm("정말 계정을 삭제할까요? 모든 데이터가 영구 삭제되며 복구할 수 없어요.")) return;
    const pw = prompt("확인을 위해 비밀번호를 입력하세요:");
    if (!pw) return;
    try {
      await api("/api/account/delete", { method: "POST", body: JSON.stringify({ password: pw }) });
    } catch (e) {
      alert("계정 삭제 실패: " + e.message);
      return;
    }
    alert("계정이 삭제되었습니다.");
    location.href = "/";
  };
  $("#setupSave").onclick = saveSetup;
  $("#setupCancel").onclick = () => $("#setupOverlay").classList.add("hidden");
  $("#sdEdit").onclick = () => openCardEditor("sd");
  $("#urgentEdit").onclick = () => openCardEditor("urgent");
  $("#chatSend").onclick = sendChat;
  $("#btnAnalyze").onclick = async () => {
    const btn = $("#btnAnalyze");
    const reset = () => {
      btn.disabled = false;
      btn.textContent = "🌙 어제 대화 분석 → 오늘 플랜 보강";
    };
    btn.disabled = true;
    btn.textContent = "분석 시작 중…";
    try {
      await api("/api/analyze", { method: "POST", body: JSON.stringify({ date: curDate }) });
    } catch (e) {
      appendChat("assistant", "분석 시작 실패: " + e);
      reset();
      return;
    }
    btn.textContent = "분석 중… (최대 1~2분)";
    // 분석을 진행하는 동안 격려 명언 한 줄
    const q = randomQuote();
    appendChat("quote", `“${q.t}”\n— ${q.a}`);
    const day = curDate;
    let tries = 0;
    const poll = setInterval(async () => {
      tries += 1;
      let s;
      try {
        s = await api(`/api/analyze/status?date=${day}`);
      } catch (e) {
        return; // 일시 오류는 다음 폴링에서 재시도
      }
      if (s.status === "done") {
        clearInterval(poll);
        reset();
        const r = s.result || {};
        const msg = r.note ? `(${r.note})`
          : `요약: ${r.summary || ""}\n추가됨: ${(r.added || []).join(", ") || "없음"}`;
        appendChat("assistant", `🌙 ${day} 보강 — 대화 ${r.messages ?? 0}개 분석\n${msg}`);
        refreshAll();
      } else if (s.status === "error") {
        clearInterval(poll);
        reset();
        appendChat("assistant", "분석 실패: " + (s.error || "") + "\n잠시 후 다시 시도해보세요.");
      } else if (tries > 60) {
        clearInterval(poll);
        reset();
        appendChat("assistant", "분석이 오래 걸려요. 잠시 후 다시 눌러보세요.");
      }
    }, 3000);
  };
  $("#chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChat();
  });
  $("#btnAddEvent").onclick = async () => {
    const event = {
      title: $("#evTitle").value.trim(),
      start: $("#evStart").value,
      end: $("#evEnd").value,
    };
    if (!event.title) return;
    await api("/api/events", { method: "POST", body: JSON.stringify({ date: curDate, event }) });
    $("#evTitle").value = "";
    replanSeed = 0;
    await api("/api/generate", { method: "POST", body: JSON.stringify({ date: curDate, seed: 0 }) });
    refreshAll();
  };
  refreshAll();
}

init();
