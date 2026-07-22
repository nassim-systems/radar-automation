from datetime import UTC, datetime, timedelta
from pathlib import Path

from radar.ingest import filter_fresh
from radar.sources.rss import parse_rss

EXPECTED_ITEM_COUNT = 2
MAX_AGE_DAYS = 30
NOW = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def test_parse_rss_sample_feed() -> None:
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")

    items = parse_rss(feed_xml)

    assert len(items) == EXPECTED_ITEM_COUNT
    assert items[0].external_id == "1"
    assert items[0].title == "First item"
    assert items[0].url == "https://example.com/1"
    assert items[0].summary == "First item summary."
    assert items[1].external_id == "2"
    assert items[1].title == "Second item"


def test_parse_rss_ignores_item_without_pubdate() -> None:
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")
    items = parse_rss(feed_xml)

    assert all(item.external_id != "3" for item in items)


def test_parse_rss_integration_with_filter_fresh() -> None:
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")
    items = parse_rss(feed_xml)

    fresh_items = filter_fresh(items, now=NOW, max_age=timedelta(days=MAX_AGE_DAYS))

    assert len(fresh_items) == len(items)
