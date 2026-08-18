from datetime import UTC, datetime, timedelta

from radar.domain import RawItem
from radar.llm.fake import FakeLLM
from radar.pipeline import PipelineConfig, ScoredDraft, run_pipeline
from radar.tools.seen_store import InMemorySeenStore

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
STALE = NOW - timedelta(days=30)
MAX_AGE = timedelta(days=7)

N_FETCHED = 5
N_DEDUP = 4
N_FRESH = 3
TOP_K = 2
LLM_CALLS = 5
SCORE = 7

N_BUDGET = 5
MAX_SCORED = 2

N_ROBUST = 3


class _BoomOnDraftLLM:
    """Fake LLM : score normalement mais lève sur le draft d'un item marqué."""

    def __init__(self, canned: str, boom_marker: str) -> None:
        self.canned = canned
        self.boom_marker = boom_marker

    def complete(self, prompt: str) -> str:
        if "brouillon" in prompt and self.boom_marker in prompt:
            raise RuntimeError("draft boom")
        return self.canned


def _item(external_id: str, title: str, published_at: datetime) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=published_at,
        summary="résumé",
    )


def _config(*, k: int, max_scored: int) -> PipelineConfig:
    return PipelineConfig(now=NOW, max_age=MAX_AGE, k=k, max_scored=max_scored)


def test_run_pipeline_end_to_end() -> None:
    items = [
        _item("1", "Alpha", FRESH),
        _item("1", "Alpha (doublon)", FRESH),
        _item("2", "Beta", FRESH),
        _item("3", "Gamma", FRESH),
        _item("4", "Vieux", STALE),
    ]
    store = InMemorySeenStore()

    report = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=FakeLLM(canned="7"),
        config=_config(k=2, max_scored=10),
    )

    assert report.n_fetched == N_FETCHED
    assert report.n_dedup == N_DEDUP
    assert report.n_fresh == N_FRESH
    assert report.n_unseen == N_FRESH
    assert report.n_scored == N_FRESH
    assert report.n_drafted == TOP_K
    assert report.n_failures == 0
    assert report.n_llm_calls == LLM_CALLS
    assert all(isinstance(d, ScoredDraft) for d in report.drafts)
    assert {d.item.external_id for d in report.drafts} == {"1", "2"}
    assert all(d.score == SCORE for d in report.drafts)


def test_run_pipeline_is_idempotent() -> None:
    items = [_item("1", "Alpha", FRESH), _item("2", "Beta", FRESH)]
    store = InMemorySeenStore()
    config = _config(k=5, max_scored=10)

    first = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=FakeLLM(canned="5"),
        config=config,
    )
    second = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=FakeLLM(canned="5"),
        config=config,
    )

    assert first.n_drafted > 0
    assert second.n_unseen == 0
    assert second.n_scored == 0
    assert second.n_drafted == 0
    assert second.drafts == []


def test_run_pipeline_respects_max_scored() -> None:
    items = [_item(str(i), f"Item {i}", FRESH) for i in range(N_BUDGET)]
    store = InMemorySeenStore()

    report = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=FakeLLM(canned="5"),
        config=_config(k=10, max_scored=MAX_SCORED),
    )

    assert report.n_unseen == N_BUDGET
    assert report.n_scored == MAX_SCORED
    assert report.n_drafted == MAX_SCORED


def test_run_pipeline_isolates_draft_failure() -> None:
    items = [
        _item("1", "Alpha", FRESH),
        _item("2", "BOOM", FRESH),
        _item("3", "Gamma", FRESH),
    ]
    store = InMemorySeenStore()

    report = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=_BoomOnDraftLLM(canned="5", boom_marker="BOOM"),
        config=_config(k=10, max_scored=10),
    )

    assert report.n_scored == N_ROBUST
    assert report.n_failures == 1
    assert report.n_drafted == N_ROBUST - 1
    assert "BOOM" not in {d.item.title for d in report.drafts}


def test_run_pipeline_retries_failed_draft() -> None:
    items = [_item("1", "Alpha", FRESH), _item("2", "BOOM", FRESH)]
    store = InMemorySeenStore()
    config = _config(k=10, max_scored=10)

    # run 1 : le draft de BOOM échoue -> BOOM n'est PAS marqué vu
    first = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=_BoomOnDraftLLM(canned="5", boom_marker="BOOM"),
        config=config,
    )
    assert first.n_failures == 1
    assert "BOOM" not in {d.item.title for d in first.drafts}

    # run 2 : LLM sain -> BOOM, resté à voir, est retenté et drafté
    second = run_pipeline(
        fetch_items=lambda: list(items),
        seen_store=store,
        llm=FakeLLM(canned="5"),
        config=config,
    )
    assert second.n_unseen == 1
    assert second.n_drafted == 1
    assert {d.item.title for d in second.drafts} == {"BOOM"}
