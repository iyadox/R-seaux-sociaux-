"""Voix off (Microsoft Edge TTS, gratuit) avec horodatage de chaque mot."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import edge_tts

TICKS_PER_SECOND = 10_000_000


@dataclass
class Word:
    text: str
    start: float
    end: float


async def _synthesize(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words: list[Word] = []
    with out.open("wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append(Word(chunk["text"], start, start + chunk["duration"] / TICKS_PER_SECOND))
    return words


def synthesize(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    return asyncio.run(_synthesize(text, voice, rate, out))
