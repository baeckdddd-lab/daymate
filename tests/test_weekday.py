import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import date
import scheduler, configlib  # noqa


def test_habit_on_day():
    assert scheduler.habit_on_day({"days": [0, 2, 4]}, 0) is True   # 월
    assert scheduler.habit_on_day({"days": [0, 2, 4]}, 1) is False  # 화
    assert scheduler.habit_on_day({}, 3) is True                    # days 없음=매일
    assert scheduler.habit_on_day({"days": []}, 3) is True          # 빈 days=매일


def test_normalize_days():
    out = configlib.normalize_habits([{"name": "운동", "blocks": 2, "days": [4, 0, 2, 9, -1]}])
    assert out[0]["days"] == [0, 2, 4] and out[0]["daily"] is False
    out2 = configlib.normalize_habits([{"name": "독서", "blocks": 1}])
    assert out2[0]["daily"] is True and "days" not in out2[0]


def _data(habits):
    return {"config": {"wake": "10:00", "sleep": "03:00",
                       "gradWindow": {"start": "11:00", "end": "16:00", "cutoff": "22:00"},
                       "fixedMeals": []},
            "habits": habits, "events": {}, "dailyGoals": {}, "gradTasks": {},
            "selfDev": {}, "fillers": {}, "conditions": {}}


def test_generate_weekday_habit_only_on_its_day():
    h = [{"name": "월수금운동", "blocks": 2, "contiguous": False, "daily": False, "days": [0]}]  # 월만
    d = date(2026, 6, 15)
    while d.weekday() != 0:
        d = date.fromordinal(d.toordinal() + 1)
    mon, tue = d.isoformat(), date.fromordinal(d.toordinal() + 1).isoformat()
    labels_mon = [s["label"] for s in scheduler.generate(mon, _data(h))["slots"]]
    labels_tue = [s["label"] for s in scheduler.generate(tue, _data(h))["slots"]]
    assert any("월수금운동" in l for l in labels_mon)
    assert not any("월수금운동" in l for l in labels_tue)
