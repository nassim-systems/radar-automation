import time
from datetime import UTC, datetime
from typing import Protocol

from core.usage import ListUsageSink, LlmUsage
from core.workflow.models import StepTrace, WorkflowRun, WorkflowState


class Step(Protocol):
    name: str

    def run(self, state: WorkflowState) -> WorkflowState: ...


class WorkflowError(Exception):
    """Raised when a step fails — carries the partial trace and the usage
    already accumulated, so the failure stays observable (not just reported).

    Never used to swallow an error: ``run_workflow`` always raises it via
    ``raise ... from error``, the original exception stays visible in the
    chain. Consistent with the policy already in place in
    ``radar/pipeline.py``: a code bug propagates — here, at the level of
    the whole step rather than the item.
    """

    def __init__(
        self,
        *,
        step_name: str,
        trace: list[StepTrace],
        usage: LlmUsage,
        original: Exception,
    ) -> None:
        self.step_name = step_name
        self.trace = trace
        self.usage = usage
        self.original = original
        super().__init__(f"step '{step_name}' failed: {original}")


def run_workflow(
    steps: list[Step],
    initial: WorkflowState,
    *,
    usage_sink: ListUsageSink | None = None,
) -> WorkflowRun:
    """Chain ``steps`` in state-passing style: each step receives the state
    returned by the previous one and returns a new (immutable) one.

    - **Abort, not skip**: if a step raises, execution stops and
      ``WorkflowError`` is raised (partial trace + usage already accumulated
      attached). A step is a complete unit of work (fetch, score,
      draft...) — silently "skipping" it would break the following steps
      that depend on its result. Fine-grained resilience (item by item,
      e.g. an isolated LLM failure) remains each step's responsibility,
      not the orchestrator's — see ``WORKFLOW.md``.
    - **Timestamps (module 4.6)**: each step carries its start and end
      instants (UTC) in addition to its monotonic duration, and the run
      carries its own. The end-to-end run latency is not the sum of the
      steps: the gap measures the orchestration cost, kept visible rather
      than dissolved. See ``OBSERVABILITY.md``.
    - **Observability reused, not reinvented**: ``usage_sink`` is the
      ``ListUsageSink`` from module 3.4, injected into the LLM clients the
      steps use internally. ``run_workflow`` only reads its aggregated total;
      it knows nothing about tokens/costs. Only the per-step duration is
      measured here, a concern the usage sink does
      not cover.
    """
    sink = usage_sink if usage_sink is not None else ListUsageSink()
    state = initial
    trace: list[StepTrace] = []
    run_started_at = datetime.now(tz=UTC)
    run_started = time.monotonic()
    for step in steps:
        step_started_at = datetime.now(tz=UTC)
        started = time.monotonic()
        try:
            state = step.run(state)
        except Exception as error:
            trace.append(
                StepTrace(
                    name=step.name,
                    started_at=step_started_at,
                    ended_at=datetime.now(tz=UTC),
                    duration_seconds=time.monotonic() - started,
                    ok=False,
                    error=str(error),
                )
            )
            raise WorkflowError(
                step_name=step.name,
                trace=trace,
                usage=sink.total(),
                original=error,
            ) from error
        trace.append(
            StepTrace(
                name=step.name,
                started_at=step_started_at,
                ended_at=datetime.now(tz=UTC),
                duration_seconds=time.monotonic() - started,
                ok=True,
            )
        )
    return WorkflowRun(
        final_state=state,
        trace=trace,
        usage=sink.total(),
        started_at=run_started_at,
        ended_at=datetime.now(tz=UTC),
        duration_seconds=time.monotonic() - run_started,
    )
