"""Génère le script d'une vidéo courte avec Claude."""

import json

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"


class Segment(BaseModel):
    text: str = Field(description="Phrase(s) lue(s) en voix off pour ce plan.")
    search_query: str = Field(description="2-4 mots-clés EN ANGLAIS pour trouver une vidéo d'illustration (stock).")


class VideoScript(BaseModel):
    topic: str
    title: str
    segments: list[Segment]
    description: str
    hashtags: list[str]


SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "Sujet précis de la vidéo, en une ligne."},
        "title": {"type": "string", "description": "Titre accrocheur, 70 caractères max, sans hashtag."},
        "segments": {
            "type": "array",
            "description": "La voix off découpée en 5 à 9 plans successifs.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "search_query": {"type": "string"},
                },
                "required": ["text", "search_query"],
                "additionalProperties": False,
            },
        },
        "description": {"type": "string", "description": "Description de 1 à 3 phrases."},
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3 à 6 hashtags pertinents, sans le caractère #.",
        },
    },
    "required": ["topic", "title", "segments", "description", "hashtags"],
    "additionalProperties": False,
}


def generate_script(channel: dict, past_topics: list[str]) -> VideoScript:
    client = anthropic.Anthropic()
    words = int(channel["target_seconds"] * 2.6)
    already = "\n".join(f"- {t}" for t in past_topics[-80:]) or "(aucun)"

    prompt = f"""Tu écris le script d'une vidéo verticale courte (YouTube Shorts / TikTok).

Thème de la chaîne : {channel['niche']}
Langue de la voix off, du titre et de la description : {channel['language']}
Style : {channel['style']}
Longueur de la voix off : environ {words} mots au total.

Sujets déjà publiés, à ne pas répéter (ni reformuler) :
{already}

Choisis un nouveau sujet précis, exact et vérifiable. N'invente aucun fait : si tu n'es pas sûr d'un chiffre, ne le donne pas.
La voix off doit être lisible telle quelle par une synthèse vocale : pas d'emoji, pas de didascalies, pas de markdown."""

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude a refusé la demande : {response.stop_details}")
    text = next(b.text for b in response.content if b.type == "text")
    return VideoScript.model_validate(json.loads(text))
