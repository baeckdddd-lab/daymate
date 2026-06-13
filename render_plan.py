"""일간 플랜을 체크리스트 PNG로 렌더 (인쇄·체크용).

배포판 전용: 동봉 나눔고딕(리눅스 한글), 파일 저장 없이 bytes만 반환.
개인앱 app/render_png.py 로직 이식 — storage 저장부 제거.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT = os.path.join(_FONT_DIR, "NanumGothic-Regular.ttf")
FONT_BOLD = os.path.join(_FONT_DIR, "NanumGothic-Bold.ttf")

COLORS = {
    "grad": (47, 95, 208), "goal": (47, 158, 107), "filler": (110, 116, 130),
    "meal": (208, 138, 47), "exercise": (208, 73, 47), "free": (130, 138, 152),
    "event": (138, 79, 208), "important": (226, 60, 90), "routine": (120, 128, 140),
    "selfdev": (40, 160, 170),
}
TYPE_KO = {
    "grad": "대학원", "goal": "할일", "filler": "filler", "meal": "식사",
    "exercise": "운동", "free": "자유", "event": "고정", "important": "중요",
    "routine": "루틴", "selfdev": "자기계발",
}

W = 860
PAD = 28
ROW_H = 34
HEAD_H = 84


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def render(plan):
    slots = plan["slots"]
    H = HEAD_H + ROW_H * len(slots) + PAD
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_title = _font(FONT_BOLD, 26)
    f_sub = _font(FONT, 14)
    f_time = _font(FONT, 15)
    f_label = _font(FONT, 16)
    f_tag = _font(FONT, 12)

    done = sum(1 for s in slots if s.get("done"))
    d.text((PAD, 24), f"{plan['date']} 데일리 플랜 체크리스트", font=f_title, fill=(20, 24, 34))
    d.text((PAD, 58), f"완료 {done} / {len(slots)} 블록", font=f_sub, fill=(120, 126, 138))
    d.line((PAD, HEAD_H - 6, W - PAD, HEAD_H - 6), fill=(220, 223, 230), width=1)

    y = HEAD_H
    for s in slots:
        color = COLORS.get(s["type"], (130, 130, 130))
        d.rectangle((PAD, y + 4, PAD + 5, y + ROW_H - 4), fill=color)
        bx0, by0 = PAD + 16, y + 7
        bx1, by1 = bx0 + 18, by0 + 18
        d.rectangle((bx0, by0, bx1, by1), outline=(80, 86, 98), width=2)
        if s.get("done"):
            d.line((bx0 + 3, by0 + 9, bx0 + 7, by1 - 4), fill=color, width=3)
            d.line((bx0 + 7, by1 - 4, bx1 - 2, by0 + 3), fill=color, width=3)
        d.text((PAD + 46, y + 8), s["range"], font=f_time, fill=(110, 116, 128))
        tag = TYPE_KO.get(s["type"], s["type"])
        tw = d.textlength(tag, font=f_tag)
        d.rectangle((PAD + 150, y + 9, PAD + 162 + tw, y + 25), fill=color)
        d.text((PAD + 156, y + 10), tag, font=f_tag, fill=(255, 255, 255))
        label = s["label"].replace("\U0001f512", "").strip()
        for pre in ("[대학원·", "[할일] ", "[습관] ", "[filler] ", "[중요] ", "[고정] ", "자기계발: "):
            if label.startswith(pre):
                label = label[len(pre):]
                if pre == "[대학원·":
                    label = label.split("] ", 1)[-1]
                break
        if s.get("note"):
            label += "  · " + s["note"].replace("\n", " ")
        lx = PAD + 175 + tw
        while label and d.textlength(label, font=f_label) > W - lx - PAD:
            label = label[:-1]
        fill = (150, 156, 168) if s.get("done") else (28, 32, 42)
        d.text((lx, y + 7), label, font=f_label, fill=fill)
        if s.get("done"):
            tw2 = d.textlength(label, font=f_label)
            ly = y + 17
            d.line((PAD + 175 + tw, ly, PAD + 175 + tw + tw2, ly), fill=(180, 184, 194), width=1)
        y += ROW_H

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
