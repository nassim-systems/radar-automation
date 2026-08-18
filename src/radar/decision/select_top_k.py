from radar.decision.models import ScoredItem
from radar.ingest import item_key


def select_top_k(scored_items: list[ScoredItem], k: int) -> list[ScoredItem]:
    """Trie par ``(-score, item_key)`` et renvoie les ``k`` meilleurs.

    Fonction pure et déterministe (aucun LLM). Ordre total : score décroissant,
    puis ``item_key`` croissant pour départager les ex æquo — reproductible et
    indépendant de l'ordre d'entrée. Un ``k`` négatif ou nul renvoie une liste
    vide ; un ``k`` supérieur au nombre d'items les renvoie tous.
    """
    ordered = sorted(
        scored_items, key=lambda scored: (-scored.score, item_key(scored.item))
    )
    return ordered[: max(k, 0)]
