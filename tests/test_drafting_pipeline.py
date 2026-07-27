from datetime import UTC, datetime

from radar.decision.models import ScoredItem
from radar.domain import RawItem
from radar.drafting.parse import Draft
from radar.drafting.pipeline import drafting_pipeline
from radar.llm.fake import FakeLLM
from radar.llm.scripted import ScriptedFakeLLM


def _scored(title: str) -> ScoredItem:
    return ScoredItem(
        item=RawItem(
            source="test",
            external_id=title,
            title=title,
            url="",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            summary=None,
        ),
        score=5,
    )


def test_drafting_pipeline_returns_one_draft_per_item() -> None:
    items = [_scored("a"), _scored("b"), _scored("c")]
    llm = FakeLLM(canned="Brouillon.")

    drafts = drafting_pipeline(items, llm)

    assert len(drafts) == len(items)
    assert all(isinstance(d, Draft) for d in drafts)
    assert all(d.text == "Brouillon." for d in drafts)


def test_drafting_pipeline_uses_prompt_per_item() -> None:
    items = [_scored("alpha"), _scored("beta")]
    llm = ScriptedFakeLLM(
        canned="défaut",
        mapping={"alpha": "Post alpha", "beta": "Post beta"},
    )

    drafts = drafting_pipeline(items, llm)

    assert [d.text for d in drafts] == ["Post alpha", "Post beta"]


def test_drafting_pipeline_empty_input() -> None:
    assert drafting_pipeline([], FakeLLM(canned="x")) == []
