from datetime import datetime, timedelta

from radar.domain import RawItem


def deduplicate(items: list[RawItem]) -> list[RawItem]:
    """Return unique items, keeping the first occurrence of each (source, external_id).

    The deduplication key is intentionally limited to (source, external_id) because
    these fields uniquely identify an item across sources. Other fields like title
    or published_at are not used for equality, to avoid dropping updated content
    from the same source item.
    """
    seen: set[tuple[str, str]] = set()
    unique_items: list[RawItem] = []

    for item in items:
        key = (item.source, item.external_id)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)

    return unique_items


def filter_fresh(
    items: list[RawItem],
    now: datetime,
    max_age: timedelta,
) -> list[RawItem]:
    return [item for item in items if now - item.published_at <= max_age]
