"""Trouve un sujet, vérifie les faits sur le web, puis écrit le script « storytelling » avec Claude."""

import json
from typing import Literal

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
SLOTS = ["center", "left", "right", "top", "bottom"]
CARD_TYPES = ["none", "chip", "big_number", "percent_ring", "progress", "document", "messages", "checklist"]
SFX = ["none", "whoosh", "pop", "ding", "boom", "typing", "error", "success", "notification"]
MOODS = ["calm", "tension", "revelation", "positive"]


class Character(BaseModel):
    id: str
    name: str
    look: str


class Asset(BaseModel):
    id: str
    prompt: str
    character_ids: list[str]


class Element(BaseModel):
    asset: str
    slot: Literal["center", "left", "right", "top", "bottom"]


class Card(BaseModel):
    type: Literal["none", "chip", "big_number", "percent_ring", "progress", "document", "messages", "checklist"]
    title: str
    value: str
    percent: float
    lines: list[str]
    tone: Literal["neutral", "good", "bad"]


class Beat(BaseModel):
    text: str
    highlight: str
    elements: list[Element]
    card: Card
    sfx: Literal["none", "whoosh", "pop", "ding", "boom", "typing", "error", "success", "notification"]
    mood: Literal["calm", "tension", "revelation", "positive"]


class VideoScript(BaseModel):
    topic: str
    title: str
    description: str
    hashtags: list[str]
    characters: list[Character]
    assets: list[Asset]
    beats: list[Beat]


def _str(desc: str) -> dict:
    return {"type": "string", "description": desc}


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic", "title", "description", "hashtags", "characters", "assets", "beats"],
    "properties": {
        "topic": _str("Sujet en une ligne."),
        "title": _str("Titre accrocheur, 70 caractères max, sans hashtag."),
        "description": _str("Description de 1 à 3 phrases, avec la source principale."),
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3 à 6 hashtags sans #."},
        "characters": {
            "type": "array",
            "description": "1 à 3 personnages récurrents de l'histoire.",
            "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "name", "look"],
                "properties": {
                    "id": _str("Identifiant court, ex. 'thomas'."),
                    "name": _str("Prénom."),
                    "look": _str("Apparence EN ANGLAIS, très précise et stable : âge, cheveux, vêtements et couleurs."),
                },
            },
        },
        "assets": {
            "type": "array",
            "description": "8 à 14 illustrations isolées (personnage dans une pose, ou objet) réutilisables dans plusieurs plans.",
            "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "prompt", "character_ids"],
                "properties": {
                    "id": _str("Identifiant court, ex. 'thomas_pays'."),
                    "prompt": _str("EN ANGLAIS : un seul sujet, sa pose/action et ses accessoires. Pas de décor, pas de texte."),
                    "character_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "beats": {
            "type": "array",
            "description": "La voix off découpée en morceaux de 3 à 12 mots, dans l'ordre.",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["text", "highlight", "elements", "card", "sfx", "mood"],
                "properties": {
                    "text": _str("Texte lu, tel quel."),
                    "highlight": _str("UN mot de `text` à colorer à l'écran (le mot-choc), ou chaîne vide."),
                    "elements": {
                        "type": "array",
                        "description": "0 à 3 illustrations visibles pendant ce morceau (état complet de l'écran).",
                        "items": {
                            "type": "object", "additionalProperties": False, "required": ["asset", "slot"],
                            "properties": {"asset": {"type": "string"}, "slot": {"type": "string", "enum": SLOTS}},
                        },
                    },
                    "card": {
                        "type": "object", "additionalProperties": False,
                        "required": ["type", "title", "value", "percent", "lines", "tone"],
                        "properties": {
                            "type": {"type": "string", "enum": CARD_TYPES},
                            "title": _str("Titre court de la carte (ou vide)."),
                            "value": _str("Valeur principale : '70 €', '12', 'Article L551-1'… (ou vide)."),
                            "percent": {"type": "number", "description": "0 à 100 pour percent_ring/progress, sinon 0."},
                            "lines": {"type": "array", "items": {"type": "string"}, "description": "Lignes de texte (document, messages, checklist ; préfixe '+' ou '-' pour checklist)."},
                            "tone": {"type": "string", "enum": ["neutral", "good", "bad"]},
                        },
                    },
                    "sfx": {"type": "string", "enum": SFX},
                    "mood": {"type": "string", "enum": MOODS},
                },
            },
        },
    },
}

RESEARCH_PROMPT = """Tu prépares une vidéo courte virale (TikTok / YouTube Shorts) en {language}.
Thème de la chaîne : {niche}

Sujets déjà traités (à ne pas refaire, même reformulés) :
{already}

Mission :
1. Cherche sur le web un sujet ORIGINAL, surprenant et utile : un droit méconnu, une aide qu'on ne réclame pas, une règle qui change tout, une étude scientifique marquante sur le comportement… Quelque chose que 90 % des gens ignorent et qui les concerne directement.
2. Vérifie chaque fait sur des sources fiables (textes officiels, service-public.fr, legifrance, études publiées, presse sérieuse). Pas de rumeur.
3. Rends un dossier court : le sujet, l'angle « histoire » (situation du quotidien où quelqu'un perd de l'argent ou se trompe sans le savoir), les faits vérifiés avec chiffres précis, ce que la personne peut faire concrètement, et les sources (URL)."""

SCRIPT_PROMPT = """Écris le script de la vidéo à partir de ce dossier vérifié :

<dossier>
{research}
</dossier>

Langue : {language}. Durée de la voix off : environ {words} mots ({seconds} secondes).

FORMAT NARRATIF (c'est ce qui rend ces vidéos captivantes, respecte-le) :
1. ACCROCHE (1re phrase) : une situation concrète avec un personnage au prénom courant et un enjeu chiffré, OU une question en « tu » qui promet une révélation (« Tu savais que… mais ce qui se passe vraiment est bien plus troublant que tu l'imagines »).
2. HISTOIRE : le personnage vit une scène banale avec des détails précis et visuels (une serviette mouillée sur le lit, 12 messages envoyés, une facture de 350 €). Il fait « comme tout le monde ».
3. BASCULE : « Sauf qu'un soir… », « Et justement… » → la révélation, avec la source précise (article de loi, étude, chercheurs) et les chiffres.
4. CONCRET : rends les chiffres tangibles (« sur 350 €, 280 € pris en charge : il ne reste que 70 € »).
5. ACTION : ce que fait le personnage / ce que les gens malins font, très concrètement (la phrase à dire, la lettre à écrire).
6. ÉLARGISSEMENT : « ton enfant, ton neveu, ta petite sœur… ça te concerne aussi ».
7. CHUTE : une dernière phrase courte et marquante, en miroir, qui reprend l'accroche.
Ton oral, tutoiement, phrases courtes, aucune formule creuse (« dans cette vidéo », « abonne-toi »). Tous les faits viennent du dossier, n'invente rien. Le texte est lu par une synthèse vocale : pas d'emoji, pas d'abréviations, écris les sigles comme ils se prononcent si besoin.

MISE EN SCÈNE :
- Style des illustrations : {art}
- `assets` : des personnages en pose (assis au bureau, qui paie, qui lit une lettre, qui s'énerve…) et des objets symboliques (bus scolaire, coffre rempli de billets, cerveau inquiet, téléphone…). Réutilise-les sur plusieurs morceaux.
- Chaque morceau (`beats`) dure 1 à 3 secondes. Change ce qu'on voit au moins toutes les 2-3 phrases : nouvel élément, nouvelle carte, nouvelle position.
- Les cartes rendent les chiffres et les textes visibles : `document` pour un texte officiel ou une lettre (lignes tapées à l'écran), `percent_ring`/`progress` pour un pourcentage, `big_number` pour un montant, `messages` pour des SMS, `checklist` pour des étapes, `chip` pour une étiquette courte (« scandale », « 2026 »). Garde la même carte (identique) sur les morceaux suivants tant qu'on en parle ; `none` pour la retirer.
- `sfx` : un bruitage seulement aux moments forts (révélation = boom, montant = ding, erreur = error, SMS = notification, texte qui s'écrit = typing). La plupart des morceaux : none.
- `mood` : calm pour l'histoire, tension pour le problème, revelation pour la bascule, positive pour la solution."""

ART = {
    "nuit": "figurines 3D en pâte à modeler, style claymation mignon, éclairage studio doux",
    "pastel": "illustration vectorielle plate façon dessin animé, contours sombres épais, couleurs vives",
}


def _call(client: anthropic.Anthropic, **kwargs):
    """Appel Claude avec repli automatique en cas de refus et reprise des tours mis en pause."""
    messages = kwargs.pop("messages")
    for _ in range(6):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
            **kwargs,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude a refusé la demande : {response.stop_details}")
        if response.stop_reason != "pause_turn":
            return response
        messages = [*messages, {"role": "assistant", "content": response.content}]
    raise RuntimeError("La recherche web n'a pas abouti.")


def generate_script(channel: dict, style: str, past_topics: list[str]) -> VideoScript:
    client = anthropic.Anthropic()
    already = "\n".join(f"- {t}" for t in past_topics[-150:]) or "(aucun)"

    research = _call(
        client,
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": RESEARCH_PROMPT.format(
            language=channel["language"], niche=channel["niche"], already=already)}],
    )
    dossier = "\n".join(b.text for b in research.content if b.type == "text")

    seconds = channel["target_seconds"]
    response = _call(
        client,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(
            research=dossier, language=channel["language"], words=int(seconds * 2.9),
            seconds=seconds, art=ART.get(style, ART["nuit"]))}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    script = VideoScript.model_validate(json.loads(text))

    # Les éléments qui pointent vers un asset inexistant sont ignorés plutôt que de faire échouer la vidéo.
    known = {a.id for a in script.assets}
    for beat in script.beats:
        beat.elements = [e for e in beat.elements if e.asset in known][:3]
    return script
