"""Exportable run trace (module 4.6, OBSERVABILITY.md).

Two levels: pure aggregations (phases, items, latencies) tested on
constructed data, then a full run through the production composition,
the only place where we can verify that the counters rebuilt by
the steps (module 4.5) and the actually traced
calls coincide.
"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.usage import ListUsageSink
from core.workflow.engine import run_workflow
from core.workflow.models import StepTrace
from radar.concurrent_scoring import ConcurrentScoringConfig
from radar.domain import RawItem
from radar.llm.timing import CallSubject, CallTimeline, LlmCallRecord
from radar.observability.trace import (
    build_run_trace,
    summarize_items,
    summarize_phases,
    write_trace_json,
)
from radar.pipeline import PipelineConfig
from radar.tools.seen_store import InMemorySeenStore
from radar.workflow import (
    RadarWorkflowState,
    build_radar_steps_production,
    radar_workflow_state_to_pipeline_report,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
MAX_AGE = timedelta(days=7)
MIN_SCORE = 8
N_ITEMS = 3
N_RELEVANT = 2
N_EXPECTED_CALLS = 7  # 3 scoring + 2 angle + 2 write
N_STEPS = 10
EXPECTED_SPEEDUP = 3.0
N_CALLS_IN_PHASE = 3
CUMULATIVE_SECONDS = 3.0
PHASE_COST_USD = 0.003
ITEM_CALLS = 3
ITEM_SECONDS = 3.5


class _ScriptedProductionLLM:
    """Same convention as ``tests/test_radar_workflow_production.py``:
    the prompt marker tells scoring / angle / writing apart."""

    def __init__(self, score_by_title: dict[str, str]) -> None:
        self._score_by_title = score_by_title

    def complete(self, prompt: str) -> str:
        if "rédige un court brouillon de post" in prompt:
            return "# Brouillon de post\nUn texte."
        if "ANGLE:" in prompt and "identifier l'angle éditorial" in prompt:
            return "ANGLE: Un angle honnête et concret pour une PME"
        for title, score in self._score_by_title.items():
            if title in prompt:
                return score
        raise AssertionError(f"prompt inattendu : {prompt[:120]}")


def _item(external_id: str, title: str) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url=f"https://x.example/{external_id}",
        published_at=FRESH,
        summary="résumé",
    )


def _call(
    phase: str, key: str | None, duration: float, cost: float = 0.001
) -> LlmCallRecord:
    return LlmCallRecord(
        phase=phase,
        subject=None if key is None else CallSubject(key=key, title=key),
        started_at=NOW,
        ended_at=NOW,
        duration_seconds=duration,
        ok=True,
        cost_usd=cost,
        input_tokens=10,
        output_tokens=2,
    )


def _step(name: str, duration: float) -> StepTrace:
    return StepTrace(
        name=name,
        started_at=NOW,
        ended_at=NOW,
        duration_seconds=duration,
        ok=True,
    )


def test_phase_speedup_compares_cumulative_calls_to_the_step_wall_time() -> None:
    """The concurrency gain measurement (module 4.3): three one-second calls
    overlapped within a one-second step amount to a speedup of 3."""
    calls = [_call("score", f"rss:{i}", duration=1.0) for i in range(3)]

    (phase,) = summarize_phases(calls, [_step("score", 1.0)])

    assert phase.cumulative_seconds == CUMULATIVE_SECONDS
    assert phase.step_wall_seconds == 1.0
    assert phase.speedup == EXPECTED_SPEEDUP
    assert phase.n_calls == N_CALLS_IN_PHASE
    assert phase.cost_usd == PHASE_COST_USD


def test_phase_without_a_matching_step_reports_no_speedup() -> None:
    (phase,) = summarize_phases([_call("score", "rss:1", 1.0)], [])

    assert phase.step_wall_seconds is None
    assert phase.speedup is None  # no denominator: no invented ratio


def test_items_aggregate_all_their_calls_across_phases() -> None:
    calls = [
        _call("score", "rss:1", 0.5),
        _call("angle", "rss:1", 1.0),
        _call("write", "rss:1", 2.0),
        _call("score", "rss:2", 0.25),
    ]

    first, second = summarize_items(calls)

    assert first.subject.key == "rss:1"
    assert first.n_calls == ITEM_CALLS
    assert first.phases == ["score", "angle", "write"]
    assert first.total_seconds == ITEM_SECONDS
    assert second.subject.key == "rss:2"


def test_calls_without_a_subject_are_left_out_of_the_item_view() -> None:
    items = summarize_items([_call("score", None, 1.0), _call("score", "rss:1", 1.0)])

    assert [item.subject.key for item in items] == ["rss:1"]


def _run_production_workflow() -> tuple[object, CallTimeline]:
    items = [
        _item("1", "Automatiser sa facturation"),
        _item("2", "Agents IA pour PME"),
        _item("3", "Résultats sportifs du week-end"),
    ]
    llm = _ScriptedProductionLLM(
        {
            "Automatiser sa facturation": "9",
            "Agents IA pour PME": "8",
            "Résultats sportifs du week-end": "1",
        }
    )
    timeline = CallTimeline()
    usage_sink = ListUsageSink()
    steps = build_radar_steps_production(
        fetch_items=lambda: items,
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=PipelineConfig(
            now=NOW, max_age=MAX_AGE, k=5, max_scored=30, min_score=MIN_SCORE
        ),
        concurrency_config=ConcurrentScoringConfig(max_concurrency=3),
        usage_sink=usage_sink,
        timeline=timeline,
    )
    return run_workflow(steps, RadarWorkflowState(), usage_sink=usage_sink), timeline


def test_production_run_traces_every_llm_call_with_its_item_and_phase() -> None:
    run, timeline = _run_production_workflow()
    report = radar_workflow_state_to_pipeline_report(run.final_state)

    trace = build_run_trace(
        report=report, workflow_run=run, calls=timeline.snapshot(), run_at=NOW
    )

    assert trace.n_llm_calls_traced == N_EXPECTED_CALLS
    # The counter rebuilt by the steps (4.5) and the calls actually
    # traced are obtained via two independent paths; they must match.
    assert trace.counters.n_llm_calls == trace.n_llm_calls_traced
    assert [phase.phase for phase in trace.phases] == ["score", "angle", "write"]
    assert [phase.n_calls for phase in trace.phases] == [
        N_ITEMS,
        N_RELEVANT,
        N_RELEVANT,
    ]
    # The off-topic item is scored then dropped: a single call for it.
    by_key = {item.subject.key: item for item in trace.items}
    assert by_key["rss:3"].phases == ["score"]
    assert by_key["rss:1"].phases == ["score", "angle", "write"]


def test_production_run_reports_step_and_run_latencies() -> None:
    run, timeline = _run_production_workflow()
    report = radar_workflow_state_to_pipeline_report(run.final_state)

    trace = build_run_trace(
        report=report, workflow_run=run, calls=timeline.snapshot(), run_at=NOW
    )

    assert len(trace.steps) == N_STEPS
    assert all(step.started_at <= step.ended_at for step in trace.steps)
    assert trace.started_at <= trace.ended_at
    assert trace.latency.run_seconds >= 0
    # The run duration is not the sum of the steps: the gap is the cost
    # of orchestration, and it is kept explicit rather than dissolved.
    assert trace.latency.orchestration_seconds >= 0
    assert trace.latency.slowest_step in {step.name for step in trace.steps}
    assert trace.latency.llm_mean_call_seconds is not None


def test_trace_is_written_as_utf8_json_and_reloads_identically(
    tmp_path: Path,
) -> None:
    run, timeline = _run_production_workflow()
    report = radar_workflow_state_to_pipeline_report(run.final_state)
    trace = build_run_trace(
        report=report, workflow_run=run, calls=timeline.snapshot(), run_at=NOW
    )

    out = tmp_path / "run_trace.json"
    write_trace_json(trace, out)
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["counters"]["n_drafted"] == report.n_drafted
    assert len(payload["calls"]) == N_EXPECTED_CALLS
    assert payload["items"][0]["subject"]["title"] == "Automatiser sa facturation"
    assert "drafts" not in payload["counters"]  # no duplication of the report


def test_empty_run_produces_a_trace_without_inventing_ratios() -> None:
    steps = build_radar_steps_production(
        fetch_items=list,
        seen_store=InMemorySeenStore(),
        llm=_ScriptedProductionLLM({}),
        config=PipelineConfig(
            now=NOW, max_age=MAX_AGE, k=5, max_scored=30, min_score=MIN_SCORE
        ),
        timeline=CallTimeline(),
    )
    run = run_workflow(steps, RadarWorkflowState())

    trace = build_run_trace(
        report=radar_workflow_state_to_pipeline_report(run.final_state),
        workflow_run=run,
        calls=[],
        run_at=NOW,
    )

    assert trace.n_llm_calls_traced == 0
    assert trace.phases == []
    assert trace.items == []
    assert trace.latency.llm_mean_call_seconds is None
    assert trace.latency.llm_slowest_call_seconds is None
