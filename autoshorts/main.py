"""Point d'entrée : génère N vidéos, les publie, et garde l'historique.

Usage :
    python -m autoshorts.main            # génère et publie
    python -m autoshorts.main --dry-run  # génère seulement (vidéo dans output/)
"""

import argparse
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import engine, images, script_gen, tts
from .uploaders import tiktok, youtube

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history.json"
OUTPUT = ROOT / "output"


def load_history() -> list[dict]:
    return json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []


def save_history(history: list[dict]) -> None:
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_video(cfg: dict, history: list[dict], workdir: Path) -> tuple[script_gen.VideoScript, Path]:
    style = cfg.get("style", "nuit")
    script = script_gen.generate_script(cfg["channel"], style, [h["topic"] for h in history])
    print(f"Sujet : {script.topic}\nTitre : {script.title}\n{len(script.beats)} morceaux, {len(script.assets)} illustrations")
    (workdir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

    assets = images.generate_assets(script, style, cfg["images"], workdir)
    print(f"{len(assets)}/{len(script.assets)} illustrations prêtes")

    narration = " ".join(b.text.strip() for b in script.beats)
    voice = workdir / "voice.mp3"
    words = tts.synthesize(narration, cfg["voice"], voice)

    OUTPUT.mkdir(exist_ok=True)
    final = OUTPUT / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.mp4"
    t0 = time.time()
    duration = engine.build(script, words, voice, assets, style, cfg, final, workdir)
    print(f"Vidéo rendue : {final} ({duration:.1f} s, montage en {time.time() - t0:.0f} s)")
    return script, final


def publish(cfg: dict, script: script_gen.VideoScript, video: Path) -> dict:
    pub = cfg["publish"]
    hashtags = " ".join(f"#{h.lstrip('#').replace(' ', '')}" for h in script.hashtags)
    results = {}
    if pub.get("youtube"):
        try:
            results["youtube"] = youtube.upload(
                video, script.title, f"{script.description}\n\n{hashtags} #Shorts",
                script.hashtags, pub["youtube_privacy"], pub["youtube_category_id"],
            )
        except Exception:
            traceback.print_exc()
            results["youtube"] = "ERREUR"
    if pub.get("tiktok"):
        try:
            results["tiktok"] = tiktok.upload(video, f"{script.title} {hashtags}", pub["tiktok_privacy"])
        except Exception:
            traceback.print_exc()
            results["tiktok"] = "ERREUR"
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Génère sans publier.")
    parser.add_argument("--count", type=int, help="Nombre de vidéos (défaut : config).")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    history = load_history()
    failures = 0

    for n in range(args.count or cfg.get("videos_per_run", 1)):
        workdir = ROOT / "work" / str(n)
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        try:
            script, video = make_video(cfg, history, workdir)
        except Exception:
            traceback.print_exc()
            failures += 1
            continue
        results = {} if args.dry_run else publish(cfg, script, video)
        print(json.dumps(results, ensure_ascii=False))
        if "ERREUR" in results.values():
            failures += 1
        history.append({
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "topic": script.topic,
            "title": script.title,
            "dry_run": args.dry_run,
            **results,
        })
        save_history(history)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
