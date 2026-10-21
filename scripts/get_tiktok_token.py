"""À lancer UNE SEULE FOIS pour obtenir le refresh token TikTok.

    export TIKTOK_CLIENT_KEY=...  TIKTOK_CLIENT_SECRET=...
    python scripts/get_tiktok_token.py https://ton-redirect-uri-enregistre/

L'URL de redirection doit être exactement celle déclarée dans ton appli
sur developers.tiktok.com (Login Kit). La page peut afficher une erreur :
ce n'est pas grave, il suffit de copier l'URL complète de la barre d'adresse.
"""

import os
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import requests

if len(sys.argv) != 2:
    sys.exit(__doc__)

redirect_uri = sys.argv[1]
client_key = os.environ["TIKTOK_CLIENT_KEY"]
client_secret = os.environ["TIKTOK_CLIENT_SECRET"]

auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
    "client_key": client_key,
    "scope": "user.info.basic,video.publish",
    "response_type": "code",
    "redirect_uri": redirect_uri,
    "state": secrets.token_urlsafe(16),
})
print(f"1. Ouvre cette adresse et autorise l'appli :\n\n{auth_url}\n")
returned = input("2. Colle ici l'URL complète vers laquelle tu as été redirigé : ").strip()
code = parse_qs(urlparse(returned).query)["code"][0]

r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    },
    timeout=30,
)
data = r.json()
if "refresh_token" not in data:
    sys.exit(f"Échec : {data}")
print("\nSecrets à ajouter dans GitHub :\n")
print(f"TIKTOK_CLIENT_KEY={client_key}")
print(f"TIKTOK_CLIENT_SECRET={client_secret}")
print(f"TIKTOK_REFRESH_TOKEN={data['refresh_token']}")
print(f"\n(refresh token valable {int(data.get('refresh_expires_in', 0)) // 86400} jours)")
