"""Publication directe sur TikTok via la Content Posting API (Direct Post)."""

import os
import subprocess
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
MAX_SINGLE_CHUNK = 64 << 20
CHUNK_SIZE = 10 << 20


def _access_token() -> str:
    r = requests.post(
        f"{API}/oauth/token/",
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"Rafraîchissement du jeton TikTok impossible : {data}")
    _persist_refresh_token(data.get("refresh_token"))
    return data["access_token"]


def _persist_refresh_token(new_token: str | None) -> None:
    """TikTok peut renvoyer un nouveau refresh token : on met à jour le secret GitHub si possible."""
    if not new_token or new_token == os.environ["TIKTOK_REFRESH_TOKEN"]:
        return
    os.environ["TIKTOK_REFRESH_TOKEN"] = new_token
    if os.environ.get("GH_PAT") and os.environ.get("GITHUB_REPOSITORY"):
        subprocess.run(
            ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
            input=new_token, text=True, check=True, env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]},
        )
        print("Secret TIKTOK_REFRESH_TOKEN mis à jour.")
    else:
        print("ATTENTION : TikTok a renvoyé un nouveau refresh token mais GH_PAT n'est pas configuré.")


def _post(path: str, token: str, payload: dict) -> dict:
    r = requests.post(
        f"{API}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        timeout=30,
    )
    body = r.json()
    if r.status_code != 200 or body.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"Erreur TikTok sur {path} : {r.status_code} {body}")
    return body["data"]


def upload(video: Path, caption: str, privacy: str) -> str:
    token = _access_token()

    creator = _post("/post/publish/creator_info/query/", token, {})
    options = creator.get("privacy_level_options", [])
    if privacy not in options:
        print(f"Confidentialité {privacy} indisponible ({options}), repli sur SELF_ONLY.")
        privacy = "SELF_ONLY"

    size = video.stat().st_size
    if size <= MAX_SINGLE_CHUNK:
        chunk_size, chunk_count = size, 1
    else:
        chunk_size, chunk_count = CHUNK_SIZE, size // CHUNK_SIZE  # le dernier morceau absorbe le reste

    init = _post("/post/publish/video/init/", token, {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
            "is_aigc": True,  # étiquette « contenu généré par IA »
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": chunk_count,
        },
    })

    with video.open("rb") as f:
        for i in range(chunk_count):
            start = i * chunk_size
            end = size - 1 if i == chunk_count - 1 else start + chunk_size - 1
            f.seek(start)
            data = f.read(end - start + 1)
            r = requests.put(
                init["upload_url"],
                data=data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
                timeout=300,
            )
            r.raise_for_status()

    publish_id = init["publish_id"]
    for _ in range(60):
        status = _post("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        if status["status"] == "PUBLISH_COMPLETE":
            ids = status.get("publicaly_available_post_id") or []
            return f"https://www.tiktok.com/video/{ids[0]}" if ids else f"tiktok publish_id={publish_id}"
        if status["status"] == "FAILED":
            raise RuntimeError(f"Publication TikTok échouée : {status.get('fail_reason')}")
        time.sleep(10)
    return f"tiktok publish_id={publish_id} (toujours en traitement)"
