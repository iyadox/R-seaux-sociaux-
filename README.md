# AutoShorts : vidéos TikTok + YouTube Shorts 100 % automatiques

Des vidéos « histoire + info méconnue » dans le style des comptes qui cartonnent (personnage, révélation, chiffres qui s'animent, chute finale), générées et publiées sans intervention humaine, plusieurs fois par jour.

## Ce qui se passe à chaque exécution

1. **Recherche (Claude + recherche web)** : trouve un sujet original dans ton thème (droit méconnu, aide non réclamée, étude marquante…), **vérifie les faits sur des sources fiables** et évite les sujets déjà publiés.
2. **Script (Claude)** : écrit l'histoire selon la structure des vidéos virales :
   accroche → personnage dans une situation banale → « Sauf que… » (la révélation sourcée) → chiffres concrets → ce qu'il faut faire → « ça te concerne aussi » → chute en miroir.
   Il découpe aussi la mise en scène : quels personnages/objets apparaissent, où, quelles cartes, quels bruitages.
3. **Illustrations** : personnages et objets générés par IA (Gemini, ou Pollinations gratuit), **avec le même personnage d'un plan à l'autre**, puis détourés automatiquement.
4. **Voix off naturelle** (ElevenLabs, ou Edge TTS gratuit), calée au mot près.
5. **Montage animé** :
   - décor animé (style « nuit » bleu avec grille et halos, ou « pastel » coloré avec rayons) qui change selon l'ambiance (calme, tension, révélation, positif) ;
   - personnages et objets qui apparaissent avec un effet « pop » et flottent ;
   - cartes animées : pourcentages qui se remplissent, montants qui défilent, texte de loi/lettre qui s'écrit, SMS qui arrivent, check-lists ;
   - sous-titres 1-3 mots avec le mot-choc en couleur ;
   - « punch » caméra sur les révélations.
6. **Son** : musique de fond qui baisse automatiquement quand la voix parle + bruitages (whoosh, pop, ding, boom, frappe clavier, notification…), volume normalisé pour les réseaux.
7. **Publication** sur YouTube Shorts et TikTok, puis enregistrement dans `data/history.json`.

Tout tourne sur **GitHub Actions** : pas de serveur ni d'ordinateur allumé.

```
config.yaml                    ← thème, style, voix, images, sons, fréquence
autoshorts/script_gen.py       ← recherche + script (Claude)
autoshorts/images.py           ← illustrations + détourage
autoshorts/tts.py              ← voix off
autoshorts/graphics.py         ← décors, cartes animées, sous-titres
autoshorts/audio.py            ← musique, bruitages, mixage
autoshorts/engine.py           ← montage image par image
autoshorts/uploaders/          ← YouTube et TikTok
scripts/get_*_token.py         ← à lancer une seule fois pour connecter les comptes
.github/workflows/autopost.yml ← planification
```

## Mise en place (une seule fois)

### 1. Clés API (Settings → Secrets and variables → Actions)
| Secret | Obligatoire ? | Où l'obtenir |
|---|---|---|
| `ANTHROPIC_API_KEY` | oui | https://console.anthropic.com |
| `ELEVENLABS_API_KEY` | recommandé (voix naturelle) | https://elevenlabs.io → Profile → API keys. Choisis une voix française dans la *Voice Library* et mets son ID dans `config.yaml` |
| `GEMINI_API_KEY` | recommandé (belles images, personnages identiques) | https://aistudio.google.com/apikey (facturation à activer) |
| `POLLINATIONS_TOKEN` | facultatif | https://auth.pollinations.ai : sans Gemini, les images gratuites sont limitées en débit |

Sans ElevenLabs ni Gemini, tout fonctionne quand même (voix Edge + images Pollinations), mais la qualité est nettement inférieure.

### 2. YouTube
1. Sur https://console.cloud.google.com : crée un projet, active **YouTube Data API v3**.
2. Écran de consentement OAuth : type *Externe*, ajoute ton adresse comme utilisateur test, puis **publie l'application** (sinon le jeton expire au bout de 7 jours).
3. Identifiants → *ID client OAuth* → **Application de bureau** → télécharge le JSON.
4. Sur ton ordinateur : `pip install google-auth-oauthlib` puis `python scripts/get_youtube_token.py client_secret.json`
5. Ajoute `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` en secrets.

### 3. TikTok
1. Sur https://developers.tiktok.com : crée une appli, ajoute **Login Kit** et **Content Posting API** (active *Direct Post*), scopes `user.info.basic` et `video.publish`, déclare une *Redirect URI* en https.
2. `export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=...` puis `python scripts/get_tiktok_token.py https://ta-redirect-uri/`
3. Ajoute `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` en secrets.
4. (Recommandé) Un *fine-grained personal access token* GitHub avec **Secrets: read and write** sur ce dépôt, en secret `GH_PAT` : le workflow mettra à jour le jeton TikTok tout seul quand il change.

### 4. Lancer
- La branche contenant le workflow doit être la **branche par défaut** du dépôt (sinon GitHub ne lance pas le planning).
- Test : onglet **Actions** → *Auto-post Shorts & TikTok* → *Run workflow* en cochant « Générer sans publier ». La vidéo est dans les artefacts du run.
- Ensuite : rien à faire, le planning publie tout seul (3 fois par jour par défaut, ligne `cron` du workflow).

## Améliorer encore le rendu
- **Musique** : dépose des musiques libres de droits (`.mp3`) dans `assets/music/` (YouTube Audio Library, Pixabay Music…). Sans fichier, une musique d'ambiance est générée automatiquement, correcte mais basique.
- **Bruitages** : tu peux remplacer n'importe quel bruitage en déposant `assets/sfx/<nom>.mp3` (`whoosh`, `pop`, `ding`, `boom`, `typing`, `error`, `success`, `notification`).
- **Style** : `style: "nuit"` ou `"pastel"` dans `config.yaml`.

## ⚠️ Limites des plateformes
- **TikTok – audit obligatoire** : tant que ton appli n'est pas auditée par TikTok, les vidéos publiées par API restent **privées**. Le code bascule automatiquement en privé dans ce cas.
- **YouTube – vérification** : un projet Google non vérifié peut voir ses vidéos bloquées en **privé** ; demande l'audit « YouTube API Services ».
- **Quota YouTube** : 6 envois par jour maximum avec le quota de base.
- **Contenu IA** : les vidéos sont déclarées comme générées par IA (`is_aigc` sur TikTok, `containsSyntheticMedia` sur YouTube), comme l'exigent les plateformes.

## Coûts estimés par vidéo
Claude (recherche + script) ≈ 0,15-0,40 € · Gemini ≈ 0,40-0,60 € (10-14 images) · ElevenLabs : ~1 300 caractères par vidéo (selon ton abonnement) · GitHub Actions : gratuit pour un dépôt public, 2 000 min/mois en privé (≈ 10-15 min par vidéo).

Test en local : `pip install -r requirements.txt`, installe ffmpeg, puis `python -m autoshorts.main --dry-run`.
