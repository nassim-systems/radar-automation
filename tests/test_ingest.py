from __future__ import annotations

from datetime import datetime, timedelta

from radar.domain import RawItem
from radar.ingest import deduplicate, filter_fresh

EXPECTED_UNIQUE_ITEMS = 2


def test_deduplicate_keeps_first_occurrence() -> None:
    items = [
        RawItem(
            source="rss",
            external_id="1",
            title="Title 1",
            url="https://example.com/1",
            published_at=datetime(2024, 1, 1, 10, 0, 0),
        ),
        RawItem(
            source="rss",
            external_id="1",
            title="Updated Title 1",
            url="https://example.com/1",
            published_at=datetime(2024, 1, 1, 11, 0, 0),
        ),
        RawItem(
            source="rss",
            external_id="2",
            title="Title 2",
            url="https://example.com/2",
            published_at=datetime(2024, 1, 2, 10, 0, 0),
        ),
    ]

    result = deduplicate(items)

    assert len(result) == EXPECTED_UNIQUE_ITEMS
    assert result[0].external_id == "1"
    assert result[0].title == "Title 1"
    assert result[1].external_id == "2"


def test_filter_fresh_returns_only_recent_items() -> None:
    now = datetime(2024, 1, 10, 12, 0, 0)
    max_age = timedelta(days=7)
    items = [
        RawItem(
            source="rss",
            external_id="1",
            title="Fresh",
            url="https://example.com/fresh",
            published_at=datetime(2024, 1, 8, 12, 0, 0),
        ),
        RawItem(
            source="rss",
            external_id="2",
            title="Stale",
            url="https://example.com/stale",
            published_at=datetime(2023, 12, 31, 12, 0, 0),
        ),
    ]

    result = filter_fresh(items, now=now, max_age=max_age)

    assert len(result) == 1
    assert result[0].external_id == "1"
