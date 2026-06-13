"""유저별 데이터 어댑터 — 기존 storage.py API를 DB(user_data/user_config)로 재현.
파일명(config.json 등)을 kind로 매핑해 scheduler가 기대하는 data dict를 만든다."""
import json
import db

_FILEMAP = {  # filename : (load_all_key, default)
    "config.json": ("config", {}),
    "goals.json": ("goals", []),
    "habits.json": ("habits", []),
    "tasks.json": ("tasks", []),
    "grad-tasks.json": ("gradTasks", {}),
    "daily-goals.json": ("dailyGoals", {}),
    "events.json": ("events", {}),
    "self-dev.json": ("selfDev", {}),
    "fillers.json": ("fillers", {}),
    "overrides.json": ("overrides", {}),
    "conditions.json": ("conditions", {}),
    "credits.json": ("credits", {}),
    "settled.json": ("settled", {}),
}
_FNAME_TO_KIND = {fn: fn[:-5] for fn in _FILEMAP}


def _get_row(s, user_id, kind, date=""):
    return s.query(db.UserData).filter_by(user_id=user_id, kind=kind, date=date).one_or_none()


def load_json(user_id, filename, default):
    kind = _FNAME_TO_KIND[filename]
    with db.SessionLocal() as s:
        if filename == "config.json":
            row = s.query(db.UserConfig).filter_by(user_id=user_id).one_or_none()
            return json.loads(row.json) if row else default
        row = _get_row(s, user_id, kind)
        return json.loads(row.json) if row else default


def save_json(user_id, filename, obj):
    kind = _FNAME_TO_KIND[filename]
    payload = json.dumps(obj, ensure_ascii=False)
    with db.SessionLocal() as s:
        if filename == "config.json":
            row = s.query(db.UserConfig).filter_by(user_id=user_id).one_or_none()
            if row: row.json = payload
            else: s.add(db.UserConfig(user_id=user_id, json=payload))
        else:
            row = _get_row(s, user_id, kind)
            if row: row.json = payload
            else: s.add(db.UserData(user_id=user_id, kind=kind, date="", json=payload))
        s.commit()


def load_all(user_id):
    return {key: load_json(user_id, fn, default) for fn, (key, default) in _FILEMAP.items()}


def save_plan(user_id, plan):
    payload = json.dumps(plan, ensure_ascii=False)
    with db.SessionLocal() as s:
        row = _get_row(s, user_id, "plan", plan["date"])
        if row: row.json = payload
        else: s.add(db.UserData(user_id=user_id, kind="plan", date=plan["date"], json=payload))
        s.commit()


def load_plan(user_id, date):
    with db.SessionLocal() as s:
        row = _get_row(s, user_id, "plan", date)
        return json.loads(row.json) if row else None


def delete_all(user_id):
    """유저의 모든 데이터(plan·config·날짜별 데이터) 영구 삭제. 계정 삭제용."""
    with db.SessionLocal() as s:
        s.query(db.UserData).filter_by(user_id=user_id).delete()
        s.query(db.UserConfig).filter_by(user_id=user_id).delete()
        s.commit()


def list_plan_dates(user_id):
    """유저가 보유한 plan 날짜를 오름차순으로 반환."""
    with db.SessionLocal() as s:
        rows = s.query(db.UserData.date).filter_by(user_id=user_id, kind="plan").all()
    return sorted(r[0] for r in rows)
