"""Décors, cartes « interface » animées et sous-titres, dessinés avec Pillow."""

import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .script_gen import Card

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


@lru_cache(maxsize=64)
def font(size: int, weight: str = "ExtraBold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)


def clean(text: str) -> str:
    """Retire les emoji et caractères absents de la police."""
    return re.sub(r"[^\u0000-ɏ‘-„…€ -ÿ]", "", text).strip()


def ease_out_back(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- Thèmes

THEMES = {
    "nuit": {
        "caption_upper": True, "caption_size": 74, "caption_y": 0.765, "caption_color": "#ffffff",
        "caption_highlight": "#ff4d6d", "caption_stroke": 0,
        "card_bg": (22, 28, 74, 235), "card_border": (120, 140, 255, 90), "card_text": "#ffffff",
        "card_muted": "#9aa6e8", "good": "#2ee59d", "bad": "#ff4d6d", "neutral": "#ffc94d",
        "paper": True,
    },
    "pastel": {
        "caption_upper": False, "caption_size": 86, "caption_y": 0.765, "caption_color": "#ffffff",
        "caption_highlight": "#ffd400", "caption_stroke": 7,
        "card_bg": (255, 255, 255, 245), "card_border": (30, 30, 50, 255), "card_text": "#1f1d2b",
        "card_muted": "#6b6880", "good": "#18b26b", "bad": "#ff4757", "neutral": "#ff9f1a",
        "paper": False,
    },
}

MOOD_COLORS = {
    "nuit": {
        "calm": ("#6a3cff", "#2b6bff"), "tension": ("#ff3b5c", "#7a2bff"),
        "revelation": ("#ffb84d", "#3ad1ff"), "positive": ("#2ee59d", "#2b6bff"),
    },
    "pastel": {
        "calm": ("#cfe3ff", "#b9d4ff"), "tension": ("#ff6b5b", "#ff8f7f"),
        "revelation": ("#5b2a86", "#7b45ad"), "positive": ("#a8e6cf", "#ffc8dd"),
    },
}


def background(style: str, mood: str, w: int, h: int) -> Image.Image:
    a, b = (hex_rgb(c) for c in MOOD_COLORS[style][mood])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if style == "nuit":
        img = np.zeros((h, w, 3), np.float32)
        img[:] = np.array([10, 13, 40], np.float32) + (yy / h)[..., None] * np.array([8, 10, 30], np.float32)
        for (cx, cy, r, col, k) in ((0.15, 0.25, 0.55, a, 0.55), (0.9, 0.55, 0.6, b, 0.45), (0.4, 0.95, 0.5, a, 0.3)):
            d = ((xx - cx * w) ** 2 + (yy - cy * h) ** 2) / (r * w) ** 2
            img += np.exp(-d * 2.2)[..., None] * np.array(col, np.float32) * k
        grid = ((xx % 54 < 2) | (yy % 54 < 2)).astype(np.float32)
        img += grid[..., None] * 14
        vignette = 1 - 0.45 * (((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2) * 2
        img *= vignette[..., None]
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    # pastel : aplat, rayons « sunburst » pour les moments forts, diagonale pour le positif
    img = np.zeros((h, w, 3), np.float32)
    img[:] = a
    if mood in ("tension", "revelation"):
        ang = np.arctan2(yy - h * 0.45, xx - w / 2)
        rays = (np.sin(ang * 12) > 0).astype(np.float32)
        img = img * (1 - rays[..., None]) + np.array(b, np.float32) * rays[..., None]
    elif mood == "positive":
        split = (xx > w * 0.55 + (yy - h / 2) * 0.25).astype(np.float32)
        img = img * (1 - split[..., None]) + np.array(b, np.float32) * split[..., None]
    else:
        grid = ((xx % 90 < 3) | (yy % 90 < 3)).astype(np.float32)
        img -= grid[..., None] * 12
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------- Cartes

CARD_W = 860


def _parse_number(value: str) -> tuple[str, float, str, int] | None:
    m = re.search(r"(-?\d[\d\s.,]*)", value)
    if not m:
        return None
    raw = m.group(1).strip()
    decimals = len(raw.split(",")[1]) if "," in raw else 0
    try:
        num = float(raw.replace(" ", "").replace(" ", "").replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return value[: m.start()], num, value[m.start() + len(m.group(1).rstrip()):], decimals


def _fmt(num: float, decimals: int) -> str:
    s = f"{num:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s


def _wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=f) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _panel(height: int, th: dict, paper: bool = False) -> Image.Image:
    img = Image.new("RGBA", (CARD_W + 40, height + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((20, 28, CARD_W + 20, height + 28), 34, fill=(0, 0, 0, 110))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    if paper:
        d.rounded_rectangle((20, 20, CARD_W + 20, height + 20), 18, fill=(250, 246, 236, 255))
    else:
        d.rounded_rectangle((20, 20, CARD_W + 20, height + 20), 34, fill=th["card_bg"], outline=th["card_border"], width=3)
    return img


def render_card(card: Card, age: float, th: dict, from_value: float | None = None) -> Image.Image:
    """Dessine la carte telle qu'elle doit apparaître `age` secondes après son apparition."""
    title, value = clean(card.title), clean(card.value)
    lines = [clean(x) for x in card.lines if clean(x)]
    tone = th[card.tone]
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    if card.type == "chip":
        text = title or value
        f = font(44, "Bold")
        tw = int(tmp.textlength(text, font=f))
        img = Image.new("RGBA", (tw + 120, 110), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((10, 10, tw + 110, 100), 45, fill=th["card_bg"], outline=tone, width=4)
        d.ellipse((34, 43, 58, 67), fill=tone)
        d.text((74, 55), text, font=f, fill=th["card_text"], anchor="lm")
        return img

    if card.type == "big_number":
        parsed = _parse_number(value)
        shown = value
        if parsed:
            pre, num, post, dec = parsed
            start = from_value if from_value is not None else 0.0
            shown = f"{pre}{_fmt(start + (num - start) * ease_out(age / 0.8), dec)}{post}"
        img = _panel(330, th)
        d = ImageDraw.Draw(img)
        if title:
            d.text((70, 70), title.upper(), font=font(34, "SemiBold"), fill=th["card_muted"])
        d.text((CARD_W / 2 + 20, 215), shown, font=font(150), fill=tone, anchor="mm")
        return img

    if card.type in ("percent_ring", "progress"):
        pct = max(0.0, min(100.0, card.percent))
        start = from_value if from_value is not None else 0.0
        cur = start + (pct - start) * ease_out(age / 0.9)
        if card.type == "percent_ring":
            img = _panel(360, th)
            d = ImageDraw.Draw(img)
            box = (70, 70, 330, 330)
            d.arc(box, 0, 360, fill=(255, 255, 255, 40) if th["paper"] else (0, 0, 0, 30), width=28)
            d.arc(box, -90, -90 + 360 * cur / 100, fill=tone, width=28)
            d.text((200, 200), f"{cur:.0f}%", font=font(76), fill=tone, anchor="mm")
            f = font(40, "Bold")
            y = 110
            for line in _wrap(d, title or value, f, CARD_W - 360)[:4]:
                d.text((380, y), line, font=f, fill=th["card_text"])
                y += 54
            return img
        img = _panel(250, th)
        d = ImageDraw.Draw(img)
        d.text((70, 60), title, font=font(40, "Bold"), fill=th["card_text"])
        if value:
            d.text((CARD_W - 30, 60), value, font=font(40, "Bold"), fill=tone, anchor="ra")
        d.rounded_rectangle((70, 150, CARD_W - 30, 200), 25, fill=(255, 255, 255, 35) if th["paper"] else (0, 0, 0, 25))
        fill_w = int((CARD_W - 100) * cur / 100)
        if fill_w > 50:
            d.rounded_rectangle((70, 150, 70 + fill_w, 200), 25, fill=tone)
        return img

    if card.type == "document":
        f_body = font(36, "SemiBold")
        body = _wrap(tmp, " ".join(lines), f_body, CARD_W - 120)[:7]
        img = _panel(200 + 52 * len(body), th, paper=th["paper"])
        d = ImageDraw.Draw(img)
        ink, muted = ((30, 30, 40), (120, 110, 100)) if th["paper"] else (th["card_text"], th["card_muted"])
        d.text((70, 60), title.upper(), font=font(28, "SemiBold"), fill=muted)
        d.text((70, 100), value, font=font(54, "Bold"), fill=ink)
        budget = int(age * 38)  # caractères tapés
        y = 185
        for line in body:
            part = line[: max(0, budget)]
            budget -= len(line)
            d.text((70, y), part, font=f_body, fill=ink)
            if 0 < len(part) < len(line) or (budget <= 0 and part == line and age % 0.8 < 0.4 and line is body[-1]):
                cx = 70 + d.textlength(part, font=f_body)
                d.rectangle((cx + 4, y + 6, cx + 8, y + 44), fill=ink)
            y += 52
        return img

    if card.type == "messages":
        f = font(38, "SemiBold")
        bubbles = [(_wrap(tmp, line, f, CARD_W - 260), i) for i, line in enumerate(lines[:5])]
        visible = [b for b in bubbles if age >= b[1] * 0.35]
        height = 150 + sum(40 + 50 * len(b[0]) for b in bubbles)
        img = _panel(height, th)
        d = ImageDraw.Draw(img)
        d.text((70, 55), title or "Messages", font=font(40, "Bold"), fill=th["card_text"])
        if visible:
            d.ellipse((CARD_W - 60, 45, CARD_W, 105), fill=th["bad"])
            d.text((CARD_W - 30, 75), str(len(visible)), font=font(34), fill="#ffffff", anchor="mm")
        y = 130
        for wrapped, i in visible:
            bw = max(int(d.textlength(x, font=f)) for x in wrapped) + 60
            bh = 50 * len(wrapped) + 30
            x0 = CARD_W - 20 - bw if i % 2 else 70
            d.rounded_rectangle((x0, y, x0 + bw, y + bh), 28, fill=th["good"] if i % 2 else (90, 110, 230))
            for k, line in enumerate(wrapped):
                d.text((x0 + 30, y + 15 + 50 * k), line, font=f, fill="#ffffff")
            y += bh + 10
        return img

    if card.type == "checklist":
        f = font(40, "Bold")
        items = lines[:6]
        img = _panel(140 + 80 * len(items), th)
        d = ImageDraw.Draw(img)
        d.text((70, 55), title, font=font(40, "Bold"), fill=th["card_text"])
        y = 135
        for i, item in enumerate(items):
            if age < i * 0.4:
                break
            bad = item.startswith("-")
            text = item.lstrip("+- ")
            col = th["bad"] if bad else th["good"]
            d.ellipse((70, y, 120, y + 50), fill=col)
            if bad:
                d.line((84, y + 14, 106, y + 36), fill="#ffffff", width=7)
                d.line((106, y + 14, 84, y + 36), fill="#ffffff", width=7)
            else:
                d.line((82, y + 26, 92, y + 37, 109, y + 14), fill="#ffffff", width=7, joint="curve")
            d.text((145, y + 25), text, font=f, fill=th["card_text"], anchor="lm")
            y += 80
        return img

    return Image.new("RGBA", (1, 1), (0, 0, 0, 0))


# ---------------------------------------------------------------- Sous-titres

def render_caption(words: list[str], highlight: set[str], th: dict, width: int) -> Image.Image:
    f = font(th["caption_size"])
    stroke = th["caption_stroke"]
    tokens = [w.upper() if th["caption_upper"] else w for w in words]
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    space = tmp.textlength(" ", font=f)
    rows, cur, cur_w = [], [], 0.0
    for raw, tok in zip(words, tokens):
        tw = tmp.textlength(tok, font=f)
        if cur and cur_w + space + tw > width - 120:
            rows.append(cur)
            cur, cur_w = [], 0.0
        cur.append((raw, tok, tw))
        cur_w += tw + (space if len(cur) > 1 else 0)
    if cur:
        rows.append(cur)
    line_h = int(th["caption_size"] * 1.2)
    img = Image.new("RGBA", (width, line_h * len(rows) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r, row in enumerate(rows):
        total = sum(t[2] for t in row) + space * (len(row) - 1)
        x = (width - total) / 2
        y = 20 + r * line_h
        for raw, tok, tw in row:
            key = re.sub(r"\W", "", raw.casefold())
            color = th["caption_highlight"] if key and key in highlight else th["caption_color"]
            if stroke:
                d.text((x, y), tok, font=f, fill=color, stroke_width=stroke, stroke_fill="#1a1a1a")
            else:
                d.text((x + 3, y + 5), tok, font=f, fill=(0, 0, 0, 150))
                d.text((x, y), tok, font=f, fill=color)
            x += tw + space
    return img


def particles(draw: ImageDraw.ImageDraw, t: float, w: int, h: int, n: int = 28) -> None:
    for i in range(n):
        speed = 18 + (i * 37 % 40)
        x = (i * 397 % w) + 20 * math.sin(t * 0.6 + i)
        y = h - ((i * 911 % h) + t * speed) % h
        r = 2 + i % 3
        alpha = int(70 + 60 * math.sin(t * 1.5 + i))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(200, 210, 255, max(0, alpha)))
