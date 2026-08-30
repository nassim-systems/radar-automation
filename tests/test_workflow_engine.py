import pytest
from pydantic import ValidationError

from core.usage import ListUsageSink, LlmUsage
from core.workflow.engine import WorkflowError, run_workflow
from core.workflow.models import WorkflowState

FIRST_VALUE = 1
AFTER_TWO_STEPS = 3


class _CounterState(WorkflowState):
    value: int = 0
    log: tuple[str, ...] = ()


class _AddStep:
    def __init__(self, name: str, amount: int) -> None:
        self.name = name
        self._amount = amount

    def run(self, state: WorkflowState) -> WorkflowState:
        assert isinstance(state, _CounterState)
        return state.model_copy(
            update={
                "value": state.value + self._amount,
                "log": (*state.log, self.name),
            }
        )


class _BoomStep:
    name = "boom"

    def run(self, state: WorkflowState) -> WorkflowState:
        raise RuntimeError("boom")


class _RecordsUsageStep:
    name = "llm_call"

    def __init__(self, sink: ListUsageSink, usage: LlmUsage) -> None:
        self._sink = sink
        self._usage = usage

    def run(self, state: WorkflowState) -> WorkflowState:
        self._sink.record(self._usage)
        return state


def test_workflow_state_is_frozen() -> None:
    state = _CounterState(value=0)
    with pytest.raises(ValidationError):
        state.value = 5  # type: ignore[misc]


def test_run_workflow_threads_state_through_steps_in_order() -> None:
    steps = [_AddStep("a", 1), _AddStep("b", 2)]

    run = run_workflow(steps, _CounterState())

    assert isinstance(run.final_state, _CounterState)
    assert run.final_state.value == AFTER_TWO_STEPS
    assert run.final_state.log == ("a", "b")


def test_run_workflow_records_trace_with_names_order_and_success() -> None:
    steps = [_AddStep("a", 1), _AddStep("b", 2)]

    run = run_workflow(steps, _CounterState())

    assert [t.name for t in run.trace] == ["a", "b"]
    assert all(t.ok for t in run.trace)
    assert all(t.duration_seconds >= 0 for t in run.trace)
    assert all(t.error is None for t in run.trace)


def test_run_workflow_empty_steps_returns_initial_state_unchanged() -> None:
    initial = _CounterState(value=FIRST_VALUE)

    run = run_workflow([], initial)

    assert run.final_state == initial
    assert run.trace == []


def test_run_workflow_creates_default_sink_when_none_provided() -> None:
    run = run_workflow([_AddStep("a", 1)], _CounterState())

    assert run.usage == LlmUsage(input_tokens=0, output_tokens=0, cost_usd=0.0)


def test_run_workflow_captures_usage_recorded_by_steps() -> None:
    sink = ListUsageSink()
    steps = [
        _RecordsUsageStep(
            sink, LlmUsage(input_tokens=10, output_tokens=2, cost_usd=0.01)
        ),
        _RecordsUsageStep(
            sink, LlmUsage(input_tokens=5, output_tokens=1, cost_usd=0.005)
        ),
    ]

    run = run_workflow(steps, _CounterState(), usage_sink=sink)

    assert run.usage == LlmUsage(input_tokens=15, output_tokens=3, cost_usd=0.015)


def test_run_workflow_aborts_on_step_failure_and_wraps_with_partial_trace() -> None:
    steps = [_AddStep("a", 1), _BoomStep(), _AddStep("c", 100)]

    with pytest.raises(WorkflowError) as exc_info:
        run_workflow(steps, _CounterState())

    error = exc_info.value
    assert error.step_name == "boom"
    assert [t.name for t in error.trace] == ["a", "boom"]
    assert error.trace[0].ok is True
    assert error.trace[1].ok is False
    assert "boom" in (error.trace[1].error or "")
    assert isinstance(error.original, RuntimeError)


def test_run_workflow_does_not_run_steps_after_a_failure() -> None:
    calls: list[str] = []

    class _TrackingStep:
        def __init__(self, name: str) -> None:
            self.name = name

        def run(self, state: WorkflowState) -> WorkflowState:
            calls.append(self.name)
            return state

    steps = [_TrackingStep("first"), _BoomStep(), _TrackingStep("never")]

    with pytest.raises(WorkflowError):
        run_workflow(steps, _CounterState())

    assert calls == ["first"]
