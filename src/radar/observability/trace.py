"""Exportable run trace (module 4.6) — the observability already produced,
made readable outside the process.

**Why a dedicated file rather than extra fields in
``run_report.json``.** ``MIGRATION.md`` §5 sets an explicit non-regression:
the ``PipelineReport`` schema is unchanged, and that is what made the
module 4.5 migration verifiable. ``RunRecord`` (hence ``run_history.json``)
depends on it directly. Grafting the trace onto it would break this
guarantee for a purely cosmetic reason. ``run_trace.json`` is thus a second
artifact, paired with the first by ``run_at`` — one more contract, none broken.

**Nothing is measured here.** This module only aggregates: per-step
durations come from ``run_workflow`` (module 4.1), calls from the
``CallTimeline`` (module 4.6), tokens and costs from the ``UsageSink``
(module 3.4). The "per phase" and "per item" views are projections of the
same call source — not parallel counters that could diverge.
"""
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from core.usage import LlmUsage
from core.workflow.models import StepTrace, WorkflowRun
from radar.llm.timing import CallSubject, LlmCallRecord
from radar.observability.models import RunRecord
from radar.observability.value import ValueEquation
from radar.pipeline import PipelineReport


class RunCounters(BaseModel):
    """The ``PipelineReport`` counters, without the drafts.

    The drafts stay in ``run_report.json``: duplicating them here would
    double the file size and create two copies to keep consistent, for
    zero new information.
    """

    n_fetched: int
    n_dedup: int
    n_fresh: int
    n_unseen: int
    n_scored: int
    n_above_threshold: int
    n_drafted: int
    n_llm_calls: int
    n_failures: int


class PhaseTiming(BaseModel):
    """Aggregate of a phase's LLM calls.

    A phase's name is, by construction, the name of the step that emits it
    (``score``, ``angle``, ``write``): this is what allows relating the
    *cumulative* call time to the step's *actual* time. Their ratio
    (``speedup``) is the direct measure of the module 4.3 concurrency gain —
    at 1.0 the step is sequential, above it the step overlaps its calls.
    """

    phase: str
    n_calls: int
    n_failures: int
    cumulative_seconds: float
    mean_seconds: float
    max_seconds: float
    step_wall_seconds: float | None = None
    speedup: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ItemTiming(BaseModel):
    """What an item cost in time and money, all calls combined."""

    subject: CallSubject
    n_calls: int
    phases: list[str]
    total_seconds: float
    cost_usd: float
    ok: bool


class LatencySummary(BaseModel):
    """Run latencies, from the most global to the finest.

    ``orchestration_seconds`` is the gap between the run's actual duration
    and the sum of the steps — the engine's own cost. Keeping it explicit
    avoids the temptation of presenting the sum of the steps as the run
    duration. ``llm_cumulative_seconds`` can exceed ``run_seconds``: this is
    expected whenever there is concurrency, and it is precisely what
    ``PhaseTiming.speedup`` measures.
    """

    run_seconds: float
    steps_seconds: float
    orchestration_seconds: float
    llm_cumulative_seconds: float
    llm_mean_call_seconds: float | None
    llm_slowest_call_seconds: float | None
    slowest_step: str | None
    slowest_step_seconds: float | None


class RunTrace(BaseModel):
    """Complete, self-contained trace of a run.

    ``n_llm_calls_traced`` is measured independently of
    ``counters.n_llm_calls`` (rebuilt by the steps, module 4.5): the two
    must match, and having obtained them by two distinct paths is what
    makes a gap visible if one appears.
    """

    run_at: datetime
    started_at: datetime
    ended_at: datetime
    counters: RunCounters
    latency: LatencySummary
    usage: LlmUsage
    n_llm_calls_traced: int
    steps: list[StepTrace] = Field(default_factory=list)
    phases: list[PhaseTiming] = Field(default_factory=list)
    items: list[ItemTiming] = Field(default_factory=list)
    calls: list[LlmCallRecord] = Field(default_factory=list)
    value: ValueEquation | None = None


class RadarRunOutcome(BaseModel):
    """What the production runner returns: the historized ``RunRecord``
    (unchanged schema, module 3.4) **and** the trace of the same run.

    Two objects rather than an enriched ``RunRecord``: the persistent history
    keeps exactly the schema it had, and the trace stays optional for any
    caller that does not consume it.
    """

    record: RunRecord
    trace: RunTrace


def summarize_phases(
    calls: list[LlmCallRecord], steps: list[StepTrace]
) -> list[PhaseTiming]:
    """Aggregate calls by phase, relating them to the same-named step."""
    wall_by_step = {step.name: step.duration_seconds for step in steps}
    order: list[str] = []
    grouped: dict[str, list[LlmCallRecord]] = {}
    for call in calls:
        if call.phase not in grouped:
            grouped[call.phase] = []
            order.append(call.phase)
        grouped[call.phase].append(call)

    phases: list[PhaseTiming] = []
    for name in order:
        group = grouped[name]
        durations = [call.duration_seconds for call in group]
        cumulative = sum(durations)
        wall = wall_by_step.get(name)
        phases.append(
            PhaseTiming(
                phase=name,
                n_calls=len(group),
                n_failures=sum(1 for call in group if not call.ok),
                cumulative_seconds=round(cumulative, 3),
                mean_seconds=round(cumulative / len(group), 3),
                max_seconds=round(max(durations), 3),
                step_wall_seconds=None if wall is None else round(wall, 3),
                speedup=(
                    round(cumulative / wall, 2)
                    if wall is not None and wall > 0
                    else None
                ),
                input_tokens=sum(call.input_tokens or 0 for call in group),
                output_tokens=sum(call.output_tokens or 0 for call in group),
                cost_usd=round(sum(call.cost_usd or 0.0 for call in group), 6),
            )
        )
    return phases


def summarize_items(calls: list[LlmCallRecord]) -> list[ItemTiming]:
    """Aggregate calls by item, in order of their first call.

    Calls without a subject (no item attached) are ignored rather than
    grouped under a catch-all key: they stay visible in ``calls`` and in
    ``phases``, where they make sense.
    """
    order: list[str] = []
    grouped: dict[str, list[LlmCallRecord]] = {}
    subjects: dict[str, CallSubject] = {}
    for call in calls:
        if call.subject is None:
            continue
        key = call.subject.key
        if key not in grouped:
            grouped[key] = []
            subjects[key] = call.subject
            order.append(key)
        grouped[key].append(call)

    return [
        ItemTiming(
            subject=subjects[key],
            n_calls=len(grouped[key]),
            phases=list(dict.fromkeys(call.phase for call in grouped[key])),
            total_seconds=round(
                sum(call.duration_seconds for call in grouped[key]), 3
            ),
            cost_usd=round(sum(call.cost_usd or 0.0 for call in grouped[key]), 6),
            ok=all(call.ok for call in grouped[key]),
        )
        for key in order
    ]


def build_run_trace(
    *,
    report: PipelineReport,
    workflow_run: WorkflowRun,
    calls: list[LlmCallRecord],
    run_at: datetime,
) -> RunTrace:
    """Assemble the exportable trace from the already-instrumented sources."""
    steps = workflow_run.trace
    steps_seconds = sum(step.duration_seconds for step in steps)
    durations = [call.duration_seconds for call in calls]
    cumulative = sum(durations)
    slowest = max(steps, key=lambda step: step.duration_seconds, default=None)

    latency = LatencySummary(
        run_seconds=round(workflow_run.duration_seconds, 3),
        steps_seconds=round(steps_seconds, 3),
        orchestration_seconds=round(
            workflow_run.duration_seconds - steps_seconds, 4
        ),
        llm_cumulative_seconds=round(cumulative, 3),
        llm_mean_call_seconds=(
            round(cumulative / len(durations), 3) if durations else None
        ),
        llm_slowest_call_seconds=round(max(durations), 3) if durations else None,
        slowest_step=None if slowest is None else slowest.name,
        slowest_step_seconds=(
            None if slowest is None else round(slowest.duration_seconds, 3)
        ),
    )

    return RunTrace(
        run_at=run_at,
        started_at=workflow_run.started_at,
        ended_at=workflow_run.ended_at,
        counters=RunCounters(**report.model_dump(exclude={"drafts"})),
        latency=latency,
        usage=workflow_run.usage,
        n_llm_calls_traced=len(calls),
        steps=steps,
        phases=summarize_phases(calls, steps),
        items=summarize_items(calls),
        calls=calls,
    )


def write_trace_json(trace: RunTrace, out: str | Path) -> None:
    """Write the trace as JSON, explicit UTF-8, same convention as
    ``write_report_json`` (independent of shell redirections)."""
    Path(out).write_text(
        json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
