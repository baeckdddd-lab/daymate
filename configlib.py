"""세팅 위저드용 순수 헬퍼: 입력 정규화 + config 부분 병합.

스케줄러/서버와 분리해 테스트 가능하게 둔다.
"""
import re

_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

# 위저드/설정 UI가 관리하는 config 키만 갱신. 그 외는 보존.
MANAGED_KEYS = {
    "wake", "sleep", "gradWindow", "fixedMeals", "freeBlocksPerDay",
    "selfDev", "fillers", "focusLabel", "setupDone",
}


def _valid_hhmm(s):
    return isinstance(s, str) and bool(_HHMM.match(s.strip()))


def normalize_habits(raw):
    """루틴 입력 정규화.
    - 이름 빈 항목 제거
    - blocks 1~8 클램프(정수)
    - daily: 항상 True (루틴=매일)
    - contiguous: bool
    - preferStart: 'HH:MM' 유효할 때만 유지(연속 아니면 스케줄러가 무시하지만 보존)
    """
    out = []
    for h in raw or []:
        if not isinstance(h, dict):
            continue
        name = (h.get("name") or "").strip()
        if not name:
            continue
        try:
            blocks = int(h.get("blocks", 1))
        except (TypeError, ValueError):
            blocks = 1
        blocks = max(1, min(8, blocks))
        # 요일별 루틴: days(0=월..6=일). 있으면 그 요일만, 없으면 매일.
        raw_days = h.get("days")
        days = sorted({int(d) for d in raw_days
                       if isinstance(d, (int, float)) and 0 <= int(d) <= 6}) \
            if isinstance(raw_days, list) else []
        item = {"name": name, "blocks": blocks,
                "contiguous": bool(h.get("contiguous"))}
        if days:
            item["days"] = days
            item["daily"] = False
        else:
            item["daily"] = True
        ps = h.get("preferStart")
        if _valid_hhmm(ps):
            item["preferStart"] = ps.strip()
        out.append(item)
    return out


def merge_config_patch(cfg, patch):
    """관리 대상 키만 patch로 갱신한 새 config 반환. 고급/민감 필드는 보존."""
    merged = dict(cfg or {})
    for k, v in (patch or {}).items():
        if k in MANAGED_KEYS:
            merged[k] = v
    return merged


def focus_label(cfg):
    return (cfg or {}).get("focusLabel") or "집중"
