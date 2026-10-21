"""Moteur de montage : cale chaque morceau sur la voix, anime les éléments et encode la vidéo."""

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from . import audio, graphics
from .script_gen import Card, VideoScript
from .tts import Word

# Emplacements : (centre x, centre y, largeur max, hauteur max), en fraction de l'écran.
SLOTS = {
    "center": (0.50, 0.46, 0.70, 0.33),
    "left": (0.28, 0.49, 0.46, 0.28),
    "right": (0.72, 0.49, 0.46, 0.28),
    "top": (0.50, 0.25, 0.55, 0.20),
    "bottom": (0.50, 0.58, 0.55, 0.17),
}
POP_IN, POP_OUT, TRANSITION = 0.35, 0.18, 0.45


@dataclass
class Span:
    key: tuple
    start: float
    end: float
    data: object = None
    from_value: float | None = None


def _norm(word: str) -> str:
    return re.sub(r"\W", "", word.casefold())


def _card_key(card: Card) -> tuple:
    return (card.type, card.title, card.value, card.percent, tuple(card.lines), card.tone)


def _spans(values: list, starts: list[float], ends: list[float]) -> list[Span]:
    """Regroupe les morceaux consécutifs qui affichent la même chose."""
    spans: list[Span] = []
    for v, s, e in zip(values, starts, ends):
        if v is None:
            continue
        key, data = v
        if spans and spans[-1].key == key and abs(spans[-1].end - s) < 1e-6:
            spans[-1].end = e
        else:
            spans.append(Span(key, s, e, data))
    return spans


def _fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    k = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)


def build(script: VideoScript, words: list[Word], voice: Path, assets: dict[str, Image.Image],
          style: str, cfg: dict, out: Path, workdir: Path) -> float:
    W, H, FPS = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    th = graphics.THEMES[style]
    beats = script.beats

    # ---- 1. Calage temporel de chaque morceau sur la voix
    positions, cursor = [], 0
    for b in beats:
        positions.append(cursor)
        cursor += len(b.text.strip()) + 1
    starts = []
    for p in positions:
        nxt = next((w.start for w in words if w.pos >= p), None)
        starts.append(nxt if nxt is not None else (starts[-1] if starts else 0.0))
    starts[0] = 0.0
    voice_end = words[-1].end if words else audio.decode(voice).shape[0] / audio.SR
    ends = starts[1:] + [voice_end + 1.2]

    # ---- 2. Ce qui est à l'écran et quand
    elem_spans: list[Span] = []
    for slot in SLOTS:
        vals = []
        for b in beats:
            e = next((e for e in b.elements if e.slot == slot and e.asset in assets), None)
            vals.append(((e.asset, slot), None) if e else None)
        elem_spans += _spans(vals, starts, ends)
    card_spans = _spans([(_card_key(b.card), b.card) if b.card.type != "none" else None for b in beats], starts, ends)
    for prev, cur in zip(card_spans, card_spans[1:]):
        # Même carte avec une nouvelle valeur : on anime le changement au lieu de la refaire apparaître.
        if prev.data.type == cur.data.type and prev.data.title == cur.data.title and abs(prev.end - cur.start) < 1e-6:
            if cur.data.type in ("percent_ring", "progress"):
                cur.from_value = prev.data.percent
            elif cur.data.type == "big_number":
                parsed = graphics._parse_number(prev.data.value)
                cur.from_value = parsed[1] if parsed else None
            else:
                cur.from_value = -1.0
    moods = [b.mood for b in beats]

    # Sous-titres : 1 à 3 mots, coupés aux pauses et aux changements de morceau.
    beat_of = lambda t: max(0, max(i for i, s in enumerate(starts) if s <= t + 1e-6))
    groups: list[list[Word]] = []
    for w in words:
        g = groups[-1] if groups else None
        if (not g or len(g) >= 3 or w.start - g[-1].end > 0.25 or beat_of(w.start) != beat_of(g[0].start)
                or len(" ".join(x.text for x in g + [w])) > 22):
            groups.append([])
        groups[-1].append(w)
    captions = []
    for i, g in enumerate(groups):
        end = groups[i + 1][0].start if i + 1 < len(groups) else g[-1].end + 0.4
        hl = {_norm(x) for x in beats[beat_of(g[0].start)].highlight.split() if _norm(x)}
        captions.append((g[0].start, end, graphics.render_caption([x.text for x in g], hl, th, W)))

    # ---- 3. Bande son : voix + musique + bruitages (ceux du script + automatiques)
    events = []
    for i, b in enumerate(beats):
        if b.sfx != "none":
            events.append((starts[i], b.sfx))
        if i and moods[i] != moods[i - 1]:
            events.append((starts[i], "whoosh"))
    for s in elem_spans + card_spans:
        if s.from_value is None and not any(abs(s.start - t) < 0.25 for t, _ in events):
            events.append((s.start, "typing" if getattr(s.data, "type", "") == "document" else "pop"))
    mixed = workdir / "mix.wav"
    total = audio.mix(voice, sorted(events), cfg["audio"], mixed)

    # ---- 4. Pré-calculs
    bgs = {m: graphics.background(style, m, W, H) for m in set(moods)}
    sized = {}
    for s in elem_spans:
        asset, slot = s.key
        if (asset, slot) not in sized:
            _, _, mw, mh = SLOTS[slot]
            sized[(asset, slot)] = _fit(assets[asset], int(mw * W), int(mh * H))
    boom_times = [t for t, n in events if n == "boom"]
    card_cache: dict = {}

    # ---- 5. Rendu image par image, envoyé directement à ffmpeg
    proc = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(mixed),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart", str(out),
    ], stdin=subprocess.PIPE)

    for f in range(int(total * FPS)):
        t = f / FPS
        bi = beat_of(t)

        # Décor (fondu entre ambiances)
        frame = bgs[moods[bi]].copy()
        if bi and moods[bi] != moods[bi - 1] and t - starts[bi] < TRANSITION:
            frame = Image.blend(bgs[moods[bi - 1]], frame, graphics.ease_out((t - starts[bi]) / TRANSITION))
        draw = ImageDraw.Draw(frame, "RGBA")
        if style == "nuit":
            graphics.particles(draw, t, W, H)

        # Carte (en haut), avec léger décalage des éléments vers le bas quand elle est là
        card_img, card_shift = None, 0.0
        for s in card_spans:
            if s.start <= t < s.end + POP_OUT:
                age = t - s.start
                anim = s.from_value is None or s.from_value >= 0
                ck = (s.key, round(age, 2) if age < 3.5 and anim else -1, s.from_value)
                if ck not in card_cache:
                    if len(card_cache) > 400:
                        card_cache.clear()
                    card_cache[ck] = graphics.render_card(s.data, age, th, s.from_value if s.from_value not in (None, -1.0) else None)
                img = card_cache[ck]
                if s.from_value is None:
                    k = graphics.ease_out_back(age / POP_IN)
                else:
                    k = 1.0
                if t >= s.end:
                    k *= 1 - graphics.ease_out((t - s.end) / POP_OUT)
                if k > 0.02:
                    card_img = img if abs(k - 1) < 1e-3 else img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))))
                card_shift = max(card_shift, min(1.0, k))
        # Éléments illustrés
        for s in elem_spans:
            if not (s.start <= t < s.end + POP_OUT):
                continue
            asset, slot = s.key
            img = sized[(asset, slot)]
            age = t - s.start
            k = graphics.ease_out_back(age / POP_IN)
            if t >= s.end:
                k *= 1 - graphics.ease_out((t - s.end) / POP_OUT)
            if k <= 0.02:
                continue
            if abs(k - 1) > 1e-3:
                img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))))
            cx, cy, _, _ = SLOTS[slot]
            bob = 10 * math.sin(2 * math.pi * 0.45 * t + hash(asset) % 7)
            x = int(cx * W - img.width / 2)
            y = int(cy * H - img.height / 2 + bob + (0.07 * H * card_shift if slot != "top" else 0))
            frame.paste(img, (x, y), img)
        if card_img is not None:
            frame.paste(card_img, (int(W / 2 - card_img.width / 2), int(0.17 * H - card_img.height / 2 + 120)), card_img)

        # Sous-titres avec petit « pop »
        for c0, c1, img in captions:
            if c0 <= t < c1:
                k = 0.86 + 0.14 * graphics.ease_out_back((t - c0) / 0.14)
                if abs(k - 1) > 1e-3:
                    img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))))
                frame.paste(img, (int(W / 2 - img.width / 2), int(th["caption_y"] * H - img.height / 2)), img)
                break

        # « Punch » de caméra sur les révélations
        punch = max((1 - (t - bt) / 0.35 for bt in boom_times if 0 <= t - bt < 0.35), default=0)
        if punch > 0:
            z = 1 + 0.06 * graphics.ease_out(punch)
            cw, ch = int(W / z), int(H / z)
            frame = frame.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H))

        proc.stdin.write(frame.convert("RGB").tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("Échec de l'encodage ffmpeg.")
    return total
