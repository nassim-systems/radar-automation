from datetime import UTC, datetime, timedelta

from core.usage import ListUsageSink, LlmUsage
from core.workflow.engine import WorkflowError, run_workflow
from radar.domain import RawItem
from radar.llm.fake import FakeLLM
from radar.pipeline import PipelineConfig
from radar.tools.seen_store import InMemorySeenStore
from radar.workflow import (
    RadarWorkflowState,
    build_radar_steps,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
STALE = NOW - timedelta(days=30)
MAX_AGE = timedelta(days=7)

EXPECTED_STEP_NAMES = [
    "fetch",
    "deduplicate",
    "filter_fresh",
    "filter_unseen",
    "score",
    "filter_by_min_score",
    "select_top_k",
    "draft",
    "mark_seen",
]
N_DRY_RUN_ITEMS = 2
N_FRESH_AFTER_DEDUP = 3  # 5 items, 1 doublon, 1 STALE -> 3 frais
SCORE = 7


class _UsageReportingFakeLLM:
    """Simulate an ``AnthropicClient``: report a fixed usage to the 3.4 sink at
    every call, as the real client would."""

    def __init__(self, canned: str, sink: ListUsageSink, per_call: LlmUsage) -> None:
        self._canned = canned
        self._sink = sink
        self._per_call = per_call

    def complete(self, prompt: str) -> str:
        self._sink.record(self._per_call)
        return self._canned


def _item(external_id: str, title: str, published_at: datetime) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=published_at,
        summary="résumé",
    )


def _config(*, k: int = 5, max_scored: int = 10, min_score: int = 0) -> PipelineConfig:
    return PipelineConfig(
        now=NOW, max_age=MAX_AGE, k=k, max_scored=max_scored, min_score=min_score
    )


def test_build_radar_steps_has_expected_order() -> None:
    steps = build_radar_steps(
        fetch_items=lambda: [],
        seen_store=InMemorySeenStore(),
        llm=FakeLLM(canned="7"),
        config=_config(),
    )

    assert [step.name for step in steps] == EXPECTED_STEP_NAMES


def test_radar_workflow_matches_known_expected_result() -> None:
    """Hard-code the values that the former equivalence proof against
    ``run_pipeline`` (module 4.1) had validated. ``run_pipeline`` was
    removed in module 4.5 (single production path, see
    ``MIGRATION.md``), so there is no direct comparison target anymore, but this
    migration step remains under guardrail."""
    items = [
        _item("1", "Alpha", FRESH),
        _item("1", "Alpha (doublon)", FRESH),
        _item("2", "Beta", FRESH),
        _item("3", "Gamma", FRESH),
        _item("4", "Vieux", STALE),
    ]
    config = _config(k=2, max_scored=10)

    steps = build_radar_steps(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=FakeLLM(canned="7"),
        config=config,
    )
    run = run_workflow(steps, RadarWorkflowState())
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)

    # 5 items -> dedup to 4 (duplicate "1") -> 3 fresh (Vieux is STALE)
    # -> all scored 7 -> top-2 by item_key ("rss:1", "rss:2").
    assert len(state.scored) == N_FRESH_AFTER_DEDUP
    assert len(state.above_threshold) == N_FRESH_AFTER_DEDUP  # min_score=0
    assert {d.item.external_id for d in state.drafts} == {"1", "2"}
    assert [d.score for d in state.drafts] == [SCORE, SCORE]


def test_radar_workflow_marks_only_drafted_items_as_seen() -> None:
    items = [_item("1", "Alpha", FRESH), _item("2", "Beta", FRESH)]
    seen_store = InMemorySeenStore()
    steps = build_radar_steps(
        fetch_items=lambda: list(items),
        seen_store=seen_store,
        llm=FakeLLM(canned="7"),
        config=_config(k=5, max_scored=10),
    )

    run_workflow(steps, RadarWorkflowState())

    assert seen_store.load_seen() == {"rss:1", "rss:2"}


def test_radar_workflow_trace_has_one_entry_per_step_all_successful() -> None:
    steps = build_radar_steps(
        fetch_items=lambda: [],
        seen_store=InMemorySeenStore(),
        llm=FakeLLM(canned="7"),
        config=_config(),
    )

    run = run_workflow(steps, RadarWorkflowState())

    assert [t.name for t in run.trace] == EXPECTED_STEP_NAMES
    assert all(t.ok for t in run.trace)
    assert all(t.duration_seconds >= 0 for t in run.trace)


def test_radar_workflow_captures_usage_across_score_and_draft_steps() -> None:
    items = [_item("1", "Alpha", FRESH)]
    sink = ListUsageSink()
    per_call = LlmUsage(input_tokens=10, output_tokens=1, cost_usd=0.001)
    llm = _UsageReportingFakeLLM(canned="7", sink=sink, per_call=per_call)
    steps = build_radar_steps(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(k=5, max_scored=10, min_score=0),
    )

    run = run_workflow(steps, RadarWorkflowState(), usage_sink=sink)

    # 1 scoring call + 1 drafting call for this item -> cumulative usage x2.
    assert run.usage == LlmUsage(input_tokens=20, output_tokens=2, cost_usd=0.002)


def test_radar_workflow_aborts_with_partial_trace_when_fetch_fails() -> None:
    def _boom() -> list[RawItem]:
        raise RuntimeError("flux indisponible")

    steps = build_radar_steps(
        fetch_items=_boom,
        seen_store=InMemorySeenStore(),
        llm=FakeLLM(canned="7"),
        config=_config(),
    )

    try:
        run_workflow(steps, RadarWorkflowState())
        raise AssertionError("aurait dû lever WorkflowError")
    except WorkflowError as error:
        assert error.step_name == "fetch"
        assert [t.name for t in error.trace] == ["fetch"]
        assert error.trace[0].ok is False


def test_radar_workflow_recomposes_a_scoring_only_dry_run() -> None:
    """Concrete proof of recomposition: a subset of the same steps
    (without draft or mark_seen) gives a scoring dry-run, without duplicating
    code or touching the seen_store; impossible with a monolithic function
    (the former ``run_pipeline``) without editing or copy-pasting it."""
    items = [_item("1", "Alpha", FRESH), _item("2", "Beta", FRESH)]
    seen_store = InMemorySeenStore()
    full_steps = build_radar_steps(
        fetch_items=lambda: list(items),
        seen_store=seen_store,
        llm=FakeLLM(canned="9"),
        config=_config(k=5, max_scored=10, min_score=0),
    )
    dry_run_steps = [s for s in full_steps if s.name not in {"draft", "mark_seen"}]

    run = run_workflow(dry_run_steps, RadarWorkflowState())
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)

    assert [t.name for t in run.trace] == [
        "fetch",
        "deduplicate",
        "filter_fresh",
        "filter_unseen",
        "score",
        "filter_by_min_score",
        "select_top_k",
    ]
    assert len(state.scored) == N_DRY_RUN_ITEMS
    assert state.drafts == []  # draft step omitted, never executed
    # mark_seen step omitted: no side effect on the store
    assert seen_store.load_seen() == set()
