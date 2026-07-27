from datetime import UTC, datetime

from radar.domain import RawItem
from radar.eval.baselines import constant_scorer, keyword_scorer

CONSTANT = 5


def _item(title: str, summary: str) -> RawItem:
    return RawItem(
        source="test",
        external_id=title,
        title=title,
        url="",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        summary=summary,
    )


def test_constant_scorer_is_always_the_same() -> None:
    assert constant_scorer(_item("peu importe", "vraiment")) == CONSTANT


def test_keyword_scorer_scores_zero_without_keywords() -> None:
    item = _item("Resultats sportifs du week-end", "le derby au bout du suspense")

    assert keyword_scorer(item) == 0


def test_keyword_scorer_rewards_pme_automation_terms() -> None:
    item = _item(
        "Automatiser la facturation avec un outil no-code",
        "un workflow pensé pour les PME",
    )

    assert keyword_scorer(item) > 0
