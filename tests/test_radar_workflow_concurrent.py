from datetime import UTC, datetime, timedelta

from core.workflow.engine import run_workflow
from radar.concurrent_scoring import ConcurrentScoringConfig
from radar.domain import RawItem
from radar.llm.fake import FakeLLM
from radar.pipeline import PipelineConfig
from radar.tools.seen_store import InMemorySeenStore
from radar.workflow import (
    ConcurrentScoreStep,
    DeduplicateStep,
    DraftStep,
    FetchStep,
    FilterByMinScoreStep,
    FilterFreshStep,
    FilterUnseenStep,
    MarkSeenStep,
    RadarWorkflowState,
    SelectTopKStep,
    build_radar_steps,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
MAX_AGE = timedelta(days=7)


def _item(external_id: str, title: str) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=FRESH,
        summary="résumé",
    )


def _config(*, k: int = 5, max_scored: int = 10, min_score: int = 0) -> PipelineConfig:
    return PipelineConfig(
        now=NOW, max_age=MAX_AGE, k=k, max_scored=max_scored, min_score=min_score
    )


def test_concurrent_score_step_is_a_drop_in_replacement_for_score_step() -> None:
    """Preuve de réutilisation : ConcurrentScoreStep remplace ScoreStep dans
    la même liste de Step, sans toucher aux autres étapes, avec un résultat
    identique sur un FakeLLM déterministe."""
    items = [_item(str(i), f"Item{i}") for i in range(4)]
    config = _config(k=2, max_scored=10)

    sequential_steps = build_radar_steps(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=FakeLLM(canned="7"),
        config=config,
    )
    sequential_run = run_workflow(sequential_steps, RadarWorkflowState())
    sequential_state = sequential_run.final_state
    assert isinstance(sequential_state, RadarWorkflowState)

    llm = FakeLLM(canned="7")
    concurrent_steps = [
        FetchStep(lambda: list(items)),
        DeduplicateStep(),
        FilterFreshStep(config),
        FilterUnseenStep(InMemorySeenStore()),
        ConcurrentScoreStep(
            llm, config, ConcurrentScoringConfig(max_concurrency=3)
        ),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        DraftStep(llm),
        MarkSeenStep(InMemorySeenStore()),
    ]
    concurrent_run = run_workflow(concurrent_steps, RadarWorkflowState())
    concurrent_state = concurrent_run.final_state
    assert isinstance(concurrent_state, RadarWorkflowState)

    assert [s.item.external_id for s in concurrent_state.scored] == [
        s.item.external_id for s in sequential_state.scored
    ]
    assert [s.score for s in concurrent_state.scored] == [
        s.score for s in sequential_state.scored
    ]
    assert [t.name for t in concurrent_run.trace] == [
        t.name for t in sequential_run.trace
    ]


def test_concurrent_score_step_respects_max_scored_from_pipeline_config() -> None:
    expected_max_scored = 2
    items = [_item(str(i), f"Item{i}") for i in range(5)]
    config = _config(max_scored=expected_max_scored)

    step = ConcurrentScoreStep(
        FakeLLM(canned="7"), config, ConcurrentScoringConfig(max_concurrency=5)
    )
    state = RadarWorkflowState(unseen=items)

    result = step.run(state)

    assert isinstance(result, RadarWorkflowState)
    assert len(result.scored) == expected_max_scored
