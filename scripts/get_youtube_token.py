"""À lancer UNE SEULE FOIS sur ton ordinateur pour obtenir le refresh token YouTube.

    pip install google-auth-oauthlib
    python scripts/get_youtube_token.py chemin/vers/client_secret.json

Un navigateur s'ouvre : connecte-toi avec le compte de la chaîne et accepte.
Copie ensuite les trois valeurs affichées dans les secrets GitHub du dépôt.
"""

import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

if len(sys.argv) != 2:
    sys.exit(__doc__)

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
info = json.loads(creds.to_json())
print("\nSecrets à ajouter dans GitHub (Settings > Secrets and variables > Actions) :\n")
print(f"YOUTUBE_CLIENT_ID={info['client_id']}")
print(f"YOUTUBE_CLIENT_SECRET={info['client_secret']}")
print(f"YOUTUBE_REFRESH_TOKEN={info['refresh_token']}")
