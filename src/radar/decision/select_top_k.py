from radar.decision.models import ScoredItem
from radar.ingest import item_key


def select_top_k(scored_items: list[ScoredItem], k: int) -> list[ScoredItem]:
    """Sort by ``(-score, item_key)`` and return the top ``k``.

    Pure, deterministic function (no LLM). Total order: score descending,
    then ``item_key`` ascending to break ties — reproducible and independent
    of input order. A negative or zero ``k`` returns an empty list; a ``k``
    greater than the number of items returns them all.
    """
    ordered = sorted(
        scored_items, key=lambda scored: (-scored.score, item_key(scored.item))
    )
    return ordered[: max(k, 0)]
