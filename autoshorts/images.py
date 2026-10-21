"""Génère les illustrations (personnages, objets) puis les détoure pour les animer sur le décor."""

import base64
import hashlib
import io
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

from .script_gen import VideoScript

STYLE = {
    "nuit": "cute 3D claymation figurine, plasticine texture, soft studio lighting, rounded stylized proportions, highly detailed, toy-like",
    "pastel": "flat 2D vector cartoon illustration, thick dark outlines, bold flat vivid colors, simple cel shading, sticker style",
}
ISOLATE = "single subject, full body, centered, isolated on a plain uniform light grey background, no text, no letters, no frame"

_rembg_session = None


def _cutout(img: Image.Image) -> Image.Image | None:
    global _rembg_session
    from rembg import new_session, remove

    if _rembg_session is None:
        _rembg_session = new_session("isnet-general-use")
    cut = remove(img.convert("RGB"), session=_rembg_session)
    bbox = cut.getbbox()
    return cut.crop(bbox) if bbox else None


def _gemini(prompt: str, refs: list[Path], model: str) -> Image.Image:
    parts = [{"text": prompt}]
    for ref in refs:
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref.read_bytes()).decode()}})
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}},
        },
        timeout=180,
    )
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            return Image.open(io.BytesIO(base64.b64decode(data["data"])))
    raise RuntimeError("Gemini n'a renvoyé aucune image.")


def _pollinations(prompt: str, seed: int) -> Image.Image:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    params = {"width": 1024, "height": 1024, "nologo": "true", "seed": seed}
    # Sans jeton, l'offre gratuite limite le débit : on attend et on réessaie.
    token = os.environ.get("POLLINATIONS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for attempt in range(6):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=180)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
            return img.crop((0, 0, img.width, int(img.height * 0.94)))  # retire le filigrane en bas
        except Exception:
            if attempt == 5:
                raise
            time.sleep(15 * (attempt + 1))
    raise AssertionError


def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest()[:7], 16)


def generate_assets(script: VideoScript, style: str, cfg: dict, workdir: Path) -> dict[str, Image.Image]:
    """Renvoie {asset_id: image RGBA détourée}. Les échecs sont ignorés (l'asset ne s'affichera pas)."""
    art = STYLE.get(style, STYLE["nuit"])
    use_gemini = cfg.get("provider") == "gemini" and bool(os.environ.get("GEMINI_API_KEY"))
    looks = {c.id: f"{c.name}: {c.look}" for c in script.characters}

    def render(prompt: str, refs: list[Path], seed_key: str) -> Image.Image:
        if use_gemini:
            try:
                return _gemini(prompt, refs, cfg["gemini_model"])
            except Exception as exc:
                print(f"Gemini a échoué ({exc}), repli sur Pollinations.")
        return _pollinations(prompt, _seed(seed_key))

    # 1. Une fiche de référence par personnage, pour qu'il soit identique dans tous les plans.
    refs: dict[str, Path] = {}
    if use_gemini:
        for c in script.characters:
            try:
                img = render(f"{art}. Character reference: {c.look}. Standing, neutral friendly pose, front view. {ISOLATE}", [], c.id)
                refs[c.id] = workdir / f"ref_{c.id}.png"
                img.save(refs[c.id])
            except Exception as exc:
                print(f"Référence de {c.name} impossible : {exc}")

    # 2. Les illustrations du script.
    def make(asset) -> tuple[str, Image.Image | None]:
        who = "; ".join(looks[cid] for cid in asset.character_ids if cid in looks)
        prompt = f"{art}. {asset.prompt}. {('Characters: ' + who + '.') if who else ''} {ISOLATE}"
        if refs and asset.character_ids:
            prompt += " Keep the characters exactly identical to the reference images."
        try:
            img = render(prompt, [refs[c] for c in asset.character_ids if c in refs], asset.character_ids[0] if asset.character_ids else asset.id)
            img.save(workdir / f"raw_{asset.id}.png")
            return asset.id, _cutout(img)
        except Exception as exc:
            print(f"Illustration « {asset.id} » impossible : {exc}")
            return asset.id, None

    with ThreadPoolExecutor(max_workers=4 if use_gemini else 1) as pool:
        results = list(pool.map(make, script.assets))
    return {asset_id: img for asset_id, img in results if img is not None}
