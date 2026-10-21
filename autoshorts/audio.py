"""Bande son : voix + musique de fond (baissée quand la voix parle) + bruitages."""

import random
import subprocess
from pathlib import Path

import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng()


def decode(path: Path) -> np.ndarray:
    """Fichier audio -> tableau float32 stéréo (n, 2) à 44,1 kHz."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _lowpass(x: np.ndarray, alpha: np.ndarray | float) -> np.ndarray:
    alpha = np.broadcast_to(alpha, x.shape)
    y, acc = np.empty_like(x), 0.0
    for i in range(len(x)):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y


def _stereo(x: np.ndarray) -> np.ndarray:
    return np.stack([x, x], axis=1).astype(np.float32)


# ---------- Bruitages synthétisés (remplaçables par des fichiers dans assets/sfx/<nom>.mp3|wav) ----------

def _whoosh() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.linspace(0, 1, n)
    shape = np.sin(np.pi * t) ** 2
    noise = rng.standard_normal(n)
    return _stereo(_lowpass(noise, 0.02 + 0.25 * shape) * shape * 1.6)


def _pop() -> np.ndarray:
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    freq = 900 * np.exp(-t * 40) + 250
    return _stereo(np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 45) * 0.8)


def _ding() -> np.ndarray:
    n = int(1.0 * SR)
    t = np.arange(n) / SR
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1568, 0.6), (3136, 0.25), (4704, 0.1)))
    return _stereo(tone * _env(n, 0.003, 0.35) * 0.6)


def _boom() -> np.ndarray:
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    freq = 40 + 70 * np.exp(-t * 6)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 3)
    hit = _lowpass(rng.standard_normal(n), 0.05) * np.exp(-t * 25)
    return _stereo((body + hit * 0.8) * 0.9)


def _typing() -> np.ndarray:
    out = np.zeros(int(0.9 * SR))
    for k in range(9):
        start = int((k * 0.095 + rng.uniform(0, 0.02)) * SR)
        click = rng.standard_normal(int(0.012 * SR)) * np.exp(-np.arange(int(0.012 * SR)) / (0.002 * SR))
        out[start:start + len(click)] += click * rng.uniform(0.25, 0.45)
    return _stereo(out)


def _two_tones(f1: float, f2: float, d: float = 0.12) -> np.ndarray:
    n = int(d * SR)
    t = np.arange(n) / SR
    a = np.sin(2 * np.pi * f1 * t) * _env(n, 0.005, d / 2)
    b = np.sin(2 * np.pi * f2 * t) * _env(n, 0.005, d / 1.5)
    return _stereo(np.concatenate([a, b]) * 0.5)


SYNTH = {
    "whoosh": _whoosh,
    "pop": _pop,
    "ding": _ding,
    "boom": _boom,
    "typing": _typing,
    "error": lambda: _two_tones(330, 220, 0.16),
    "success": lambda: _two_tones(784, 1175),
    "notification": lambda: _two_tones(1318, 1760, 0.09),
}


def sfx(name: str) -> np.ndarray:
    for ext in ("wav", "mp3"):
        f = ROOT / "assets" / "sfx" / f"{name}.{ext}"
        if f.exists():
            return decode(f)
    return SYNTH[name]()


# ---------- Musique ----------

def _procedural_music(seconds: float) -> np.ndarray:
    """Petite boucle lo-fi douce (pad + arpège + rythmique légère), générée à la volée."""
    bpm = 90
    beat = 60 / bpm
    progressions = [
        [(57, 60, 64, 67), (53, 57, 60, 64), (48, 52, 55, 59), (55, 59, 62, 64)],  # Am7 Fmaj7 Cmaj7 G6
        [(50, 53, 57, 60), (55, 58, 62, 65), (48, 52, 55, 58), (53, 57, 60, 64)],  # Dm7 Gm7 C7 Fmaj7
    ]
    chords = random.choice(progressions)
    bar = 4 * beat
    n_total = int(seconds * SR) + SR
    out = np.zeros(n_total)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)

    n_bar = int(bar * SR)
    t_bar = np.arange(n_bar) / SR
    pad_env = np.minimum(1, t_bar / 0.6) * np.minimum(1, (bar - t_bar) / 0.4)
    pluck_n = int(beat / 2 * SR)
    t_pl = np.arange(pluck_n) / SR
    kick_n = int(0.3 * SR)
    t_k = np.arange(kick_n) / SR
    kick = np.sin(2 * np.pi * np.cumsum(50 + 60 * np.exp(-t_k * 30)) / SR) * np.exp(-t_k * 12)

    for b in range(int(seconds / bar) + 2):
        start = int(b * bar * SR)
        if start >= n_total:
            break
        chord = chords[b % 4]
        pad = sum(np.sin(2 * np.pi * hz(m) * t_bar * d) for m in chord for d in (1.0, 1.003)) / 8
        bass = np.sin(2 * np.pi * hz(chord[0] - 12) * t_bar) * 0.35
        seg = (pad * 0.5 + bass) * pad_env
        if b >= 2:  # l'arpège et la rythmique arrivent après l'intro
            for k in range(8):
                note = chord[[0, 2, 1, 3, 2, 1, 3, 2][k]] + 12
                pl = np.sin(2 * np.pi * hz(note) * t_pl) * np.exp(-t_pl * 9) * 0.22
                s = int(k * beat / 2 * SR)
                seg[s:s + pluck_n] += pl[: max(0, min(pluck_n, n_bar - s))]
            for k in (0, 2):
                s = int(k * beat * SR)
                seg[s:s + kick_n] += kick[: max(0, min(kick_n, n_bar - s))] * 0.5
        end = min(n_total, start + n_bar)
        out[start:end] += seg[: end - start]

    out = _lowpass(out, 0.35)
    return _stereo(out / (np.abs(out).max() + 1e-9) * 0.8)


def music(seconds: float) -> np.ndarray:
    files = sorted((ROOT / "assets" / "music").glob("*.mp3")) + sorted((ROOT / "assets" / "music").glob("*.wav"))
    if files:
        track = decode(random.choice(files))
        reps = int(np.ceil(seconds * SR / len(track))) + 1
        return np.tile(track, (reps, 1))
    return _procedural_music(seconds)


# ---------- Mixage ----------

def mix(voice_path: Path, events: list[tuple[float, str]], cfg: dict, out: Path, tail: float = 1.2) -> float:
    """Mixe voix + musique + bruitages dans `out` (wav). Renvoie la durée totale."""
    voice = decode(voice_path)
    n = len(voice) + int(tail * SR)
    track = np.zeros((n, 2), np.float32)
    track[: len(voice)] += voice

    # Ducking : la musique baisse quand la voix parle et remonte dans les silences.
    win = int(0.05 * SR)
    frames = len(voice) // win
    rms = np.sqrt((voice[: frames * win, 0].reshape(frames, win) ** 2).mean(axis=1))
    speaking = np.convolve((rms > 0.02).astype(float), np.ones(6) / 6, mode="same")
    gain = np.interp(np.arange(n), np.arange(frames) * win, cfg["music_volume"] * (1.8 - 0.8 * speaking))
    bed = music(n / SR)[:n]
    fade = np.minimum(1, np.minimum(np.arange(n) / (0.5 * SR), (n - np.arange(n)) / (1.0 * SR)))
    track += bed * (gain * fade)[:, None]

    cache: dict[str, np.ndarray] = {}
    for t, name in events:
        if name not in SYNTH:
            continue
        s = cache.setdefault(name, sfx(name))
        start = int(t * SR)
        end = min(n, start + len(s))
        if start < n:
            track[start:end] += s[: end - start] * cfg["sfx_volume"]

    track /= max(1.0, float(np.abs(track).max()) / 0.95)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-", str(out)],
        input=track.astype(np.float32).tobytes(), check=True,
    )
    return n / SR
