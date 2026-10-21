"""Assemble la vidéo verticale : plans d'illustration + voix off + sous-titres incrustés."""

import random
import subprocess
from pathlib import Path

from .tts import Word

FALLBACK_COLORS = ["0x1d3557", "0x6a040f", "0x283618", "0x3a0ca3", "0x003049", "0x5f0f40", "0x264653"]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def render_segment(clip: Path | None, duration: float, out: Path, w: int, h: int, fps: int) -> None:
    """Un plan de `duration` secondes, recadré en vertical. Sans clip : fond dégradé animé."""
    if clip is not None:
        inputs = ["-stream_loop", "-1", "-i", str(clip)]
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},eq=brightness=-0.06"
    else:
        c0, c1 = random.sample(FALLBACK_COLORS, 2)
        inputs = ["-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0={c0}:c1={c1}:speed=0.02:r={fps}"]
        vf = "setsar=1"
    run([
        "ffmpeg", "-y", *inputs, "-t", f"{duration:.3f}", "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out),
    ])


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_subtitles(words: list[Word], out: Path, w: int, h: int, words_per_caption: int) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,86,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Groupes de N mots, en coupant aussi à chaque pause (fin de phrase).
    groups: list[list[Word]] = []
    for word in words:
        if not groups or len(groups[-1]) >= words_per_caption or word.start - groups[-1][-1].end > 0.25:
            groups.append([])
        groups[-1].append(word)

    lines = []
    for i, group in enumerate(groups):
        # Le sous-titre reste affiché jusqu'au groupe suivant, pour éviter les clignotements.
        end = groups[i + 1][0].start if i + 1 < len(groups) else group[-1].end + 0.3
        text = " ".join(word.text for word in group).upper().replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ass_time(group[0].start)},{_ass_time(end)},Default,,0,0,0,,{text}")
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def assemble(segments: list[Path], audio: Path, subtitles: Path, out: Path, workdir: Path) -> None:
    concat_list = workdir / "segments.txt"
    concat_list.write_text("".join(f"file '{s.resolve()}'\n" for s in segments))
    sub_path = str(subtitles.resolve()).replace("\\", "/").replace(":", r"\:")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(audio),
        "-vf", f"subtitles='{sub_path}'", "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", "-movflags", "+faststart", str(out),
    ])
