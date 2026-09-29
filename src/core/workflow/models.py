from datetime import datetime

from pydantic import BaseModel, ConfigDict

from core.usage import LlmUsage


class WorkflowState(BaseModel):
    """Base state of a workflow.

    ``frozen=True`` makes immutability structural, not merely
    conventional: a step cannot mutate the state it receives (an attempt
    raises ``pydantic.ValidationError``), it must return a new instance
    (``state.model_copy(update={...})``). Each concrete workflow defines
    its own subclass with typed business fields — see ``WORKFLOW.md``
    (decision "typing of WorkflowState").
    """

    model_config = ConfigDict(frozen=True)


class StepTrace(BaseModel):
    """Execution trace of a step: name, timestamps, duration, outcome.

    ``started_at``/``ended_at`` are UTC instants (wall clock): they place the
    step in real time and allow correlating it with the LLM calls it
    triggered. ``duration_seconds`` is still measured separately with
    ``time.monotonic()``, unaffected by clock adjustments. The two are
    therefore not redundant — this is deliberate: one locates, the other
    measures.
    """

    name: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    ok: bool
    error: str | None = None


class WorkflowRun(BaseModel):
    """Result of a successful ``run_workflow``: final state, trace, aggregated usage.

    ``usage`` reuses ``LlmUsage``/``UsageSink`` from module 3.4 (tokens,
    cost) — no parallel observability reinvented here. Per-step duration
    (``StepTrace.duration_seconds``), for its part, is an orchestration
    concern that the LLM usage sink does not cover; it is measured
    directly by ``run_workflow``.

    ``duration_seconds`` (module 4.6) is the **end-to-end** latency of the
    run — not the sum of the steps: the gap between the two is the
    orchestration cost itself, and it must stay visible rather than be
    dissolved in a sum.
    """

    final_state: WorkflowState
    trace: list[StepTrace]
    usage: LlmUsage
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
