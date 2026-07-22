from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from radar.ingest import filter_fresh
from radar.sources.rss import parse_rss


def test_parse_rss_sample_feed():
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")

    items = parse_rss(feed_xml)

    assert len(items) == 2
    assert items[0].external_id == "1"
    assert items[0].title == "First item"
    assert items[0].url == "https://example.com/1"
    assert items[0].summary == "First item summary."
    assert items[1].external_id == "2"
    assert items[1].title == "Second item"


def test_parse_rss_ignores_item_without_pubdate():
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")
    items = parse_rss(feed_xml)

    assert all(item.external_id != "3" for item in items)


def test_parse_rss_integration_with_filter_fresh():
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")
    items = parse_rss(feed_xml)

    now = datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    fresh_items = filter_fresh(items, now=now, max_age=timedelta(days=30))

    assert len(fresh_items) == len(items)
