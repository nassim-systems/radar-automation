from pydantic import BaseModel

from radar.domain import RawItem


class ScoredItem(BaseModel):
    item: RawItem
    score: int


def select_top_k(scored_items: list[ScoredItem], k: int) -> list[ScoredItem]:
    """Trie les items par score décroissant et renvoie les ``k`` meilleurs.

    Fonction pure et déterministe (aucun LLM). Le tri est stable : à score
    égal, l'ordre d'entrée est préservé. Un ``k`` négatif ou nul renvoie une
    liste vide ; un ``k`` supérieur au nombre d'items les renvoie tous.
    """
    ordered = sorted(scored_items, key=lambda scored: scored.score, reverse=True)
    return ordered[: max(k, 0)]
