"""Voix off avec horodatage de chaque mot : ElevenLabs (naturelle) ou Edge TTS (gratuite)."""

import asyncio
import base64
import os
import re
from dataclasses import dataclass
from pathlib import Path

import edge_tts
import requests

TICKS_PER_SECOND = 10_000_000


@dataclass
class Word:
    text: str
    start: float
    end: float
    pos: int  # position du mot dans le texte complet


def _elevenlabs(text: str, cfg: dict, out: Path) -> list[Word]:
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['elevenlabs_voice_id']}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={
            "text": text,
            "model_id": cfg["elevenlabs_model"],
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True},
        },
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    out.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data["alignment"]
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words = []
    for m in re.finditer(r"\S+", "".join(chars)):
        token = m.group().strip(".,;:!?…«»\"()")
        if token:
            words.append(Word(token, starts[m.start()], ends[m.end() - 1], m.start()))
    return words


async def _edge(text: str, cfg: dict, out: Path) -> list[Word]:
    communicate = edge_tts.Communicate(text, cfg["edge_voice"], rate=cfg["edge_rate"], boundary="WordBoundary")
    words, cursor, lower = [], 0, text.lower()
    with out.open("wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                pos = lower.find(chunk["text"].lower(), cursor)
                if pos < 0:
                    pos = cursor
                else:
                    cursor = pos + len(chunk["text"])
                words.append(Word(chunk["text"], start, start + chunk["duration"] / TICKS_PER_SECOND, pos))
    return words


def synthesize(text: str, cfg: dict, out: Path) -> list[Word]:
    if cfg.get("provider") == "elevenlabs" and os.environ.get("ELEVENLABS_API_KEY"):
        try:
            return _elevenlabs(text, cfg, out)
        except Exception as exc:
            print(f"ElevenLabs indisponible ({exc}), repli sur Edge TTS.")
    return asyncio.run(_edge(text, cfg, out))
