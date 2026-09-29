from datetime import UTC, datetime

from radar.decision.models import ScoredItem
from radar.decision.select_top_k import select_top_k
from radar.domain import RawItem


def _scored(title: str, score: int) -> ScoredItem:
    return ScoredItem(
        item=RawItem(
            source="test",
            external_id=title,
            title=title,
            url="",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            summary=None,
        ),
        score=score,
    )


def test_select_top_k_returns_highest_scores_descending() -> None:
    items = [_scored("a", 3), _scored("b", 9), _scored("c", 5)]

    top = select_top_k(items, 2)

    assert [s.item.title for s in top] == ["b", "c"]
    assert [s.score for s in top] == [9, 5]


def test_select_top_k_breaks_ties_by_item_key() -> None:
    # same score, input order reverse of item_key: sort follows item_key
    items = [_scored("b", 5), _scored("a", 5), _scored("c", 5)]

    top = select_top_k(items, 2)

    assert [s.item.external_id for s in top] == ["a", "b"]


def test_select_top_k_clamps_k_above_length() -> None:
    items = [_scored("a", 1), _scored("b", 2)]

    top = select_top_k(items, 10)

    assert len(top) == len(items)


def test_select_top_k_returns_empty_for_non_positive_k() -> None:
    items = [_scored("a", 1)]

    assert select_top_k(items, 0) == []
    assert select_top_k(items, -3) == []


def test_select_top_k_does_not_mutate_input() -> None:
    items = [_scored("a", 1), _scored("b", 9)]
    original = list(items)

    select_top_k(items, 1)

    assert items == original
