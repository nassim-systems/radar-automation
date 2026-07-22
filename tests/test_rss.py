from pathlib import Path
import sys

# Ensure that src is on sys.path so tests can import the radar package.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "src"
sys.path.insert(0, str(SRC))

from radar.rss import parse_rss


def test_parse_rss_sample_feed():
    feed_path = ROOT / "fixtures" / "sample_feed.xml"
    items = parse_rss(feed_path)

    assert len(items) == 2
    assert items[0].external_id == "1"
    assert items[0].title == "First item"
    assert items[0].url == "https://example.com/1"
    assert items[0].summary == "First item summary."
    assert items[1].external_id == "2"
    assert items[1].title == "Second item"


def test_parse_rss_ignores_item_without_pubdate():
    feed_path = ROOT / "fixtures" / "sample_feed.xml"
    items = parse_rss(feed_path)

    assert all(item.external_id != "3" for item in items)
