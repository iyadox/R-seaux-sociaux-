# AutoShorts : vidéos TikTok + YouTube Shorts 100 % automatiques

À chaque exécution planifiée (par défaut 3 fois par jour), sans intervention humaine :

1. **Claude** choisit un nouveau sujet dans ton thème (en évitant ceux déjà publiés) et écrit le script, le titre, la description et les hashtags.
2. **Edge TTS** (gratuit) génère la voix off, avec l'horodatage de chaque mot.
3. **Pexels** (gratuit) fournit des vidéos d'illustration libres de droits pour chaque plan (sinon : fond dégradé animé).
4. **ffmpeg** assemble une vidéo verticale 1080×1920 avec des sous-titres dynamiques incrustés.
5. La vidéo est publiée sur **YouTube Shorts** (API YouTube Data v3) et sur **TikTok** (Content Posting API, publication directe).
6. Le sujet est ajouté à `data/history.json` pour ne jamais le refaire.

Tout tourne sur **GitHub Actions** : pas de serveur ni d'ordinateur allumé.

```
config.yaml                 ← thème, langue, voix, fréquence, confidentialité
autoshorts/main.py          ← orchestration
autoshorts/script_gen.py    ← script avec Claude
autoshorts/tts.py           ← voix off
autoshorts/visuals.py       ← clips Pexels
autoshorts/render.py        ← montage ffmpeg + sous-titres
autoshorts/uploaders/       ← YouTube et TikTok
scripts/get_*_token.py      ← à lancer une seule fois pour connecter les comptes
.github/workflows/autopost.yml ← planification
```

## Mise en place (une seule fois)

### 1. Clés API
| Secret GitHub | Où l'obtenir |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys |
| `PEXELS_API_KEY` | https://www.pexels.com/api/ (gratuit) |

### 2. YouTube
1. Sur https://console.cloud.google.com : crée un projet, active **YouTube Data API v3**.
2. Écran de consentement OAuth : type *Externe*, ajoute ton adresse comme utilisateur test, puis **publie l'application** (sinon le refresh token expire au bout de 7 jours).
3. Identifiants → *Créer un ID client OAuth* → type **Application de bureau** → télécharge le JSON.
4. Sur ton ordinateur : `pip install google-auth-oauthlib` puis `python scripts/get_youtube_token.py client_secret.json`
5. Ajoute `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` dans les secrets GitHub.

### 3. TikTok
1. Sur https://developers.tiktok.com : crée une appli, ajoute les produits **Login Kit** et **Content Posting API** (active *Direct Post*), scopes `user.info.basic` et `video.publish`, déclare une *Redirect URI* en https.
2. `export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=...` puis `python scripts/get_tiktok_token.py https://ta-redirect-uri/`
3. Ajoute `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` dans les secrets GitHub.
4. (Recommandé) Crée un *fine-grained personal access token* GitHub avec la permission **Secrets: read and write** sur ce dépôt et enregistre-le en secret `GH_PAT` : si TikTok renouvelle le refresh token, le workflow mettra le secret à jour tout seul.

### 4. Lancer
- Test : onglet **Actions** → *Auto-post Shorts & TikTok* → *Run workflow* en cochant « Générer sans publier ». La vidéo est téléchargeable dans les artefacts du run.
- Ensuite, plus rien à faire : le planning (`cron` dans le workflow) publie automatiquement.

## ⚠️ Limites des plateformes à connaître

- **TikTok – audit obligatoire** : tant que ton appli n'a pas passé l'audit de TikTok, les vidéos publiées par API sont **privées (SELF_ONLY)**. Le code bascule automatiquement en privé dans ce cas. Demande l'audit depuis le portail développeur pour publier en public.
- **YouTube – vérification** : les vidéos envoyées par un projet Google non vérifié peuvent être bloquées en **privé**. Il faut demander l'audit de l'API YouTube (formulaire « YouTube API Services – Audit and Quota Extension »).
- **Quota YouTube** : 10 000 unités/jour par défaut, un envoi = 1 600 unités → **6 vidéos/jour maximum**.
- **Contenu IA** : les vidéos sont automatiquement déclarées comme générées par IA (`is_aigc` sur TikTok, `containsSyntheticMedia` sur YouTube), comme l'exigent les deux plateformes. Les deux plateformes pénalisent le contenu répétitif ou de faible qualité publié en masse : mieux vaut 1 à 3 vidéos/jour soignées que 20 vidéos identiques.

## Coûts estimés
- Claude : quelques centimes par vidéo.
- Edge TTS, Pexels, GitHub Actions (dépôt public, ou 2 000 min/mois en privé) : gratuit.

## Personnaliser
Tout se règle dans `config.yaml` : thème (`niche`), langue, style, durée, voix, nombre de vidéos par exécution. La fréquence se règle dans la ligne `cron` de `.github/workflows/autopost.yml`.

Test en local : `pip install -r requirements.txt`, installe ffmpeg, puis `python -m autoshorts.main --dry-run`.
