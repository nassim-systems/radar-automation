from datetime import datetime

from radar.domain import RawItem
from radar.llm.fake import FakeLLM
from radar.scoring import Score, build_prompt, parse_score, score_item


def _make_item() -> RawItem:
    return RawItem(
        source="rss",
        external_id="1",
        title="Titre",
        url="https://example.com/1",
        published_at=datetime(2024, 1, 1, 0, 0, 0),
        summary="Un résumé",
    )


def test_build_prompt_includes_item_fields() -> None:
    item = _make_item()

    prompt = build_prompt(item)

    assert item.title in prompt
    assert item.summary in prompt
    assert "PME" in prompt  # cadrage automatisation-PME


def test_build_prompt_is_pure() -> None:
    item = _make_item()

    first = build_prompt(item)
    second = build_prompt(item)

    assert first == second
    assert item == _make_item()


def test_parse_score_reads_integer() -> None:
    assert parse_score("7") == Score(score=7)


def test_parse_score_strips_whitespace() -> None:
    assert parse_score("  4\n") == Score(score=4)


def test_parse_score_returns_neutral_for_non_numeric_output() -> None:
    assert parse_score("pas un nombre") == Score(score=0)


def test_parse_score_returns_neutral_for_empty_output() -> None:
    assert parse_score("") == Score(score=0)


def test_score_item_uses_llm_output() -> None:
    item = _make_item()
    llm = FakeLLM(canned="9")

    assert score_item(item, llm) == Score(score=9)


def test_score_item_returns_neutral_when_llm_output_malformed() -> None:
    item = _make_item()
    llm = FakeLLM(canned="n'importe quoi")

    assert score_item(item, llm) == Score(score=0)
