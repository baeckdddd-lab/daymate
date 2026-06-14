"""웹푸시(VAPID) 발송 + 스케줄 판단 로직.

전송은 pywebpush, 시각 판단은 순수 함수(due_kinds)로 분리해 테스트 가능하게.
한국시각 = UTC+9 고정(대한민국은 DST 없음) → zoneinfo/tzdata 의존 회피.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import userstore

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUB = os.environ.get("VAPID_CLAIM_SUB", "mailto:admin@daymate.app")

KST = timezone(timedelta(hours=9))

DEFAULT_PREFS = {"morning": True, "slot": True, "evening": True,
                 "midnight": True, "reward": True}

# 슬롯 리마인더는 '꼭 챙길' 타입만 → 알림 피로/이탈 방지(의미블록 전부면 하루 5~10개).
SLOT_REMINDER_TYPES = {"important", "grad", "exercise"}

# 알림 문구(오타 검수본). {label}/{pct}/{coins}는 호출부에서 채움.
MSG = {
    "morning": ("☀️ 좋은 아침!", "오늘 플랜을 확인하고 시작해요."),
    "slot": ("⏱️ 지금 할 시간", "{label}"),
    "evening": ("🌙 오늘 어땠어요?", "잠깐 회고하고 내일을 준비해요."),
    "midnight_warn": ("⏰ 자정 마감 임박", "오늘 할 일 다 체크했어요? 자정 지나면 크레딧이 잠겨요."),
    "midnight_settle": ("🎉 어제 정산 완료", "어제 달성률 {pct}% · +{coins} 크레딧!"),
    "reward": ("🔥 100% 달성!", "오늘 플랜을 완벽하게 지켰어요. +{coins} 크레딧!"),
}


def kst_now():
    return datetime.now(timezone.utc).astimezone(KST)


def due_kinds(hour, minute):
    """현재 시각(한국)에 발송할 '고정시각' 알림 종류 집합.

    크론은 30분 간격(:00/:30, 약간의 지터)이라 30분 창으로 판단.
    슬롯 리마인더는 매 틱마다 유저별로 따로 판단하므로 여기 포함하지 않음.
    """
    kinds = set()
    if hour == 10 and minute < 30:
        kinds.add("morning")
    if hour == 23 and minute < 30:
        kinds.add("evening")
    if hour == 23 and minute >= 30:
        kinds.add("midnight_warn")
    if hour == 0 and minute < 30:
        kinds.add("midnight_settle")
    return kinds


def get_push(user_id):
    p = userstore.load_json(user_id, "push.json", {})
    p.setdefault("subscriptions", [])
    prefs = dict(DEFAULT_PREFS)
    prefs.update(p.get("prefs", {}))
    p["prefs"] = prefs
    return p


def add_subscription(user_id, sub):
    p = get_push(user_id)
    endpoint = sub.get("endpoint")
    p["subscriptions"] = [s for s in p["subscriptions"] if s.get("endpoint") != endpoint]
    p["subscriptions"].append(sub)
    userstore.save_json(user_id, "push.json", p)
    return True


def set_prefs(user_id, prefs):
    p = get_push(user_id)
    for k in DEFAULT_PREFS:
        if k in prefs:
            p["prefs"][k] = bool(prefs[k])
    userstore.save_json(user_id, "push.json", p)
    return p["prefs"]


def should_send_reward(user_id, date):
    """100% 보상 푸시를 오늘 아직 안 보냈고 구독·pref가 있으면 True(그리고 표시)."""
    p = get_push(user_id)
    if not p["subscriptions"] or not p["prefs"].get("reward"):
        return False
    if p.get("rewardSent") == date:
        return False
    p["rewardSent"] = date
    userstore.save_json(user_id, "push.json", p)
    return True


def _send_one(subscription, payload):
    """단일 구독 발송. True=성공, False=만료(404/410, 제거 대상)."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=subscription,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": VAPID_SUB})
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):
            return False
        raise


def send_to_user(user_id, title, body, url="/"):
    """유저의 모든 구독에 발송하고 만료 구독을 정리. 성공 발송 수 반환."""
    p = get_push(user_id)
    subs = p.get("subscriptions", [])
    payload = {"title": title, "body": body, "url": url}
    alive, sent = [], 0
    for sub in subs:
        try:
            ok = _send_one(sub, payload)
        except Exception:
            ok = True  # 일시 오류는 구독 유지(다음 틱 재시도)
            alive.append(sub)
            continue
        if ok:
            alive.append(sub)
            sent += 1
        # ok False(만료) → drop
    if len(alive) != len(subs):
        p["subscriptions"] = alive
        userstore.save_json(user_id, "push.json", p)
    return sent
