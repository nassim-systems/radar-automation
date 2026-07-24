from datetime import datetime, timedelta

from radar.domain import RawItem


def item_key(item: RawItem) -> str:
    return f"{item.source}:{item.external_id}"


def deduplicate(items: list[RawItem]) -> list[RawItem]:
    """Return unique items, keeping the first occurrence of each source/external_id."""
    seen: set[str] = set()
    unique_items: list[RawItem] = []

    for item in items:
        key = item_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)

    return unique_items


def filter_unseen(items: list[RawItem], seen: set[str]) -> list[RawItem]:
    return [item for item in items if item_key(item) not in seen]


def filter_fresh(
    items: list[RawItem],
    now: datetime,
    max_age: timedelta,
) -> list[RawItem]:
    return [item for item in items if now - item.published_at <= max_age]
