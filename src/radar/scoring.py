from pydantic import BaseModel

from radar.domain import RawItem
from radar.llm.base import LLMClient

NEUTRAL_SCORE = 0


class Score(BaseModel):
    score: int


def build_prompt(item: RawItem) -> str:
    """Construit un prompt texte simple à partir d'un ``RawItem``.

    Fonction pure : sortie déterministe, aucune mutation de l'item,
    aucune logique LLM.
    """
    return (
        "Évalue la pertinence de cet article sur une échelle de 0 à 10.\n"
        "Réponds uniquement par un entier, sans aucun autre texte.\n\n"
        f"Titre : {item.title}\n"
        f"Source : {item.source}\n"
        f"URL : {item.url}\n"
        f"Résumé : {item.summary or ''}\n"
    )


def parse_score(raw: str) -> Score:
    """Parse la sortie brute du LLM en un ``Score``.

    Fonction pure.

    Décision d'architecte — sortie malformée :
        En cas de sortie non parsable en entier, on renvoie un ``Score``
        neutre (``score=0``) plutôt que de lever une exception. Le radar
        traite les items en lot ; une seule réponse mal formée ne doit
        pas interrompre tout le pipeline. Un score neutre relègue
        simplement l'item au plus bas rang. Ce choix est cohérent avec
        la résilience déjà en place ailleurs (``JsonSeenStore.load_seen``
        renvoie un ensemble vide sur JSON corrompu au lieu de lever).
    """
    try:
        value = int(raw.strip())
    except ValueError:
        return Score(score=NEUTRAL_SCORE)
    return Score(score=value)


def score_item(item: RawItem, llm: LLMClient) -> Score:
    prompt = build_prompt(item)
    raw = llm.complete(prompt)
    return parse_score(raw)
