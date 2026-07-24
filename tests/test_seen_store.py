from datetime import datetime
from pathlib import Path

from radar.domain import RawItem
from radar.ingest import filter_unseen, item_key
from radar.sources.rss import parse_rss
from radar.tools.seen_store import JsonSeenStore

ROOT = Path(__file__).resolve().parents[1]


def test_json_seen_store_round_trip(tmp_path: Path) -> None:
    store = JsonSeenStore(tmp_path / "seen.json")

    store.add_seen(["a", "b"])
    result = store.load_seen()

    assert result == {"a", "b"}


def test_json_seen_store_loads_empty_when_missing(tmp_path: Path) -> None:
    store = JsonSeenStore(tmp_path / "missing.json")

    assert store.load_seen() == set()


def test_json_seen_store_loads_empty_for_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.json"
    path.write_text("%%%", encoding="utf-8")

    store = JsonSeenStore(path)

    assert store.load_seen() == set()


def test_filter_unseen_is_pure() -> None:
    seen = {"rss:a", "rss:b"}
    items = [
        RawItem(
            source="rss",
            external_id="a",
            title="A",
            url="https://example.com/a",
            published_at=datetime(2024, 1, 1, 0, 0, 0),
        ),
        RawItem(
            source="rss",
            external_id="b",
            title="B",
            url="https://example.com/b",
            published_at=datetime(2024, 1, 1, 0, 0, 0),
        ),
        RawItem(
            source="rss",
            external_id="c",
            title="C",
            url="https://example.com/c",
            published_at=datetime(2024, 1, 1, 0, 0, 0),
        ),
    ]

    result = filter_unseen(items, seen)

    assert [item.external_id for item in result] == ["c"]


def test_ingestion_idempotence(tmp_path: Path) -> None:
    fixture_path = ROOT / "fixtures" / "sample_feed.xml"
    feed_xml = fixture_path.read_text(encoding="utf-8")
    items = parse_rss(feed_xml)
    store = JsonSeenStore(tmp_path / "seen.json")

    first_run = filter_unseen(items, store.load_seen())
    assert first_run == items

    seen_keys = {item_key(item) for item in first_run}
    store.add_seen(seen_keys)

    second_run = filter_unseen(items, store.load_seen())
    assert second_run == []
