"""Récupère des vidéos d'illustration libres de droits sur Pexels."""

import os
import random
from pathlib import Path

import requests

PEXELS_SEARCH = "https://api.pexels.com/videos/search"


def _pick_file(video: dict) -> str | None:
    # Fichier vertical le plus proche de 1080 px de large, sans dépasser 1440.
    files = [f for f in video["video_files"] if f.get("width") and f.get("height")]
    files = [f for f in files if f["height"] >= f["width"] and f["width"] <= 1440] or files
    if not files:
        return None
    return min(files, key=lambda f: abs(f["width"] - 1080))["link"]


def fetch_clip(query: str, out: Path, used_ids: set[int]) -> Path | None:
    """Télécharge un clip correspondant à la requête. Renvoie None si rien n'est trouvé."""
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    for orientation in ("portrait", None):
        params = {"query": query, "per_page": 15, "size": "medium"}
        if orientation:
            params["orientation"] = orientation
        r = requests.get(PEXELS_SEARCH, params=params, headers={"Authorization": api_key}, timeout=30)
        r.raise_for_status()
        videos = [v for v in r.json().get("videos", []) if v["id"] not in used_ids and v["duration"] >= 3]
        random.shuffle(videos)
        for video in videos:
            link = _pick_file(video)
            if not link:
                continue
            with requests.get(link, stream=True, timeout=120) as dl:
                dl.raise_for_status()
                with out.open("wb") as f:
                    for block in dl.iter_content(1 << 20):
                        f.write(block)
            used_ids.add(video["id"])
            return out
    return None
