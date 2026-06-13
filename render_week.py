"""주간 타임테이블을 캘린더형 PNG로 렌더 (파스텔, 연속 일정 병합).

배포판 전용: 폰트는 동봉한 나눔고딕(리눅스/Railway 호환), 파일 저장 없이 bytes만 반환.
개인앱 app/render_week_png.py 로직 이식 — storage.PLANS 저장부 제거.
"""
import io
import os
import re
from datetime import date

from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT = os.path.join(_FONT_DIR, "NanumGothic-Regular.ttf")
FONT_BOLD = os.path.join(_FONT_DIR, "NanumGothic-Bold.ttf")

# type -> (bg, text, accent)
PASTEL = {
    "grad": ((225, 233, 252), (42, 75, 145), (138, 163, 232)),
    "goal": ((221, 242, 232), (29, 115, 80), (108, 199, 158)),
    "selfdev": ((217, 241, 244), (21, 115, 123), (107, 197, 207)),
    "meal": ((253, 240, 219), (147, 96, 15), (238, 192, 116)),
    "exercise": ((252, 226, 219), (173, 58, 34), (240, 160, 143)),
    "event": ((239, 227, 252), (102, 64, 159), (187, 155, 228)),
    "important": ((252, 224, 232), (171, 41, 66), (240, 143, 163)),
    "filler": ((238, 240, 245), (88, 96, 115), (188, 196, 209)),
    "free": ((244, 246, 249), (139, 147, 163), (212, 218, 227)),
    "routine": ((238, 240, 245), (107, 114, 128), (198, 204, 214)),
}
GRAD = (47, 95, 208)
LINE = (228, 231, 238)
PAD = 16
TIME_W = 44
DAY_W = 150
TITLE_H = 30
HEAD_H = 48
ROW_H = 22


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _short(label):
    s = label.replace("\U0001f512", "").strip()
    s = re.sub(r"^\[대학원·[^\]]*\]\s*", "", s)
    s = re.sub(r"^\[(할일|습관|filler|중요|고정)\]\s*", "", s)
    s = re.sub(r"^자기계발:\s*", "자기계발 ", s)
    return s


def _fmt_hour(hhmm):
    h = int(hhmm[:2])
    ap = "AM" if h < 12 else "PM"
    hh = h % 12 or 12
    return f"{hh}{ap}"


def render(week):
    days = week["days"]
    n = len(days[0]["slots"])
    W = PAD * 2 + TIME_W + DAY_W * 7
    H = PAD * 2 + TITLE_H + HEAD_H + ROW_H * n
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_title = _font(FONT_BOLD, 20)
    f_dow = _font(FONT, 11)
    f_date = _font(FONT_BOLD, 17)
    f_time = _font(FONT, 10)
    f_ev = _font(FONT_BOLD, 11)
    f_evr = _font(FONT, 9)
    today = date.today().isoformat()

    d.text((PAD, 10), f"주간 타임테이블   {days[0]['date']} ~ {days[6]['date']}",
           font=f_title, fill=(28, 34, 48))
    gx = PAD
    gy = PAD + TITLE_H
    grid_top = gy + HEAD_H

    # 헤더
    for i, day in enumerate(days):
        cx = gx + TIME_W + DAY_W * i
        is_today = day["date"] == today
        d.text((cx + DAY_W // 2, gy + 8), day["dow"], font=f_dow,
               fill=GRAD if is_today else (120, 126, 138), anchor="ma")
        num = day["date"][8:]
        if is_today:
            tw = d.textlength(num, font=f_date)
            cxn = cx + DAY_W // 2
            d.rounded_rectangle((cxn - tw / 2 - 9, gy + 22, cxn + tw / 2 + 9, gy + 44),
                                radius=11, fill=GRAD)
            d.text((cxn, gy + 24), num, font=f_date, fill=(255, 255, 255), anchor="ma")
        else:
            d.text((cx + DAY_W // 2, gy + 22), num, font=f_date,
                   fill=(40, 46, 60), anchor="ma")
    d.line((gx, grid_top, gx + TIME_W + DAY_W * 7, grid_top), fill=LINE, width=1)

    # 시간선 + 라벨
    for r in range(n):
        start = days[0]["slots"][r]["range"].split("–")[0]
        if start[3:] == "00":
            y = grid_top + r * ROW_H
            d.line((gx, y, gx + TIME_W + DAY_W * 7, y), fill=LINE, width=1)
            d.text((gx + TIME_W - 4, y + 1), _fmt_hour(start), font=f_time,
                   fill=(150, 156, 168), anchor="ra")
    # 세로 구분선
    for i in range(8):
        lx = gx + TIME_W + DAY_W * i
        d.line((lx, grid_top, lx, grid_top + ROW_H * n), fill=LINE, width=1)

    # 이벤트 병합 블록
    for i, day in enumerate(days):
        cx = gx + TIME_W + DAY_W * i
        r = 0
        slots = day["slots"]
        while r < n:
            s = slots[r]
            length = 1
            while (r + length < n and slots[r + length]["label"] == s["label"]
                   and slots[r + length]["type"] == s["type"]):
                length += 1
            bg, txt, acc = PASTEL.get(s["type"], ((238, 240, 245), (90, 90, 90), (190, 190, 190)))
            x0, y0 = cx + 3, grid_top + r * ROW_H + 2
            x1, y1 = cx + DAY_W - 3, grid_top + (r + length) * ROW_H - 2
            d.rounded_rectangle((x0, y0, x1, y1), radius=6, fill=bg)
            d.rounded_rectangle((x0, y0, x0 + 3, y1), radius=2, fill=acc)
            label = _short(s["label"])
            while label and d.textlength(label, font=f_ev) > DAY_W - 18:
                label = label[:-1]
            d.text((x0 + 9, y0 + 3), label, font=f_ev, fill=txt)
            if length >= 2:
                endR = slots[r + length - 1]["range"].split("–")[1]
                rng = f"{s['range'].split(chr(0x2013))[0]}–{endR}"
                d.text((x0 + 9, y0 + 18), rng, font=f_evr, fill=txt)
            r += length

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
