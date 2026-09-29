"""Timing instrumentation of LLM calls (module 4.6).

``LLMClient`` decorator — not a modification of ``AnthropicClient``. The
reason is the same as for the module 3.4 ``UsageSink``: the real client
has no need to know about observability, and a decorator lets the tests'
``FakeLLM``/``ScriptedLLM`` be instrumented the same way as the
production client, with no conditional code.

**Per-item attribution.** The decorator carries the call's *subject* (the
current item) and its *phase* (the step name). Attribution is therefore
explicit at the call site, not guessed afterwards: each step creates a
decorator per item. It is the call-side counterpart of module 4.1's step trace.

**Usage attribution (tokens/cost).** ``CallTimeline`` also implements
``UsageSink``: plugged via ``TeeUsageSink`` next to the existing
``ListUsageSink``, it receives the real usage of the same call and attaches
it to the current call. Correlation goes through a *thread-local* variable
and this is deliberately correct: ``AnthropicClient.complete`` notifies its
sink synchronously, in the thread running the call — the same as the
decorator's, including in the concurrent scoring ``ThreadPoolExecutor``
(module 4.3). No token/cost counting is reinvented here: the source
remains the usage returned by the SDK.
"""
import threading
import time
from datetime import UTC, datetime

from pydantic import BaseModel

from core.usage import LlmUsage
from radar.llm.base import LLMClient


class CallSubject(BaseModel):
    """What an LLM call is about — in practice, a feed item."""

    key: str
    title: str
    url: str | None = None


class LlmCallRecord(BaseModel):
    """An LLM call actually issued: when, how long, on what,
    with what outcome and what usage.

    A *retry* (module 4.3) produces one record per attempt — it is the
    number of calls actually issued to the API that is traced, not the
    number of items processed. ``PipelineReport.n_llm_calls`` must therefore
    match ``len(calls)``: a divergence between the two counters would be a
    bug, and having measured them independently makes it visible.
    """

    phase: str
    subject: CallSubject | None = None
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    ok: bool
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class _InFlight:
    """Mutable slot for the in-progress call in the current thread.

    Deliberately outside Pydantic: it is an internal mechanics detail,
    never serialized, never exposed.
    """

    __slots__ = ("usage",)

    def __init__(self) -> None:
        self.usage: LlmUsage | None = None


class CallTimeline:
    """Journal of a run's LLM calls, safe in a concurrent environment.

    Implements ``UsageSink`` (``record`` method) to receive the real usage
    of the in-progress call — see the module docstring for the correctness
    of per-thread attribution.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._local = threading.local()
        self.calls: list[LlmCallRecord] = []

    def record(self, usage: LlmUsage) -> None:
        """``UsageSink``: attach the usage to the in-progress call in THIS thread.

        A usage received outside any instrumented call is ignored rather than
        attributed at random to another call: better a missing field
        than a wrong figure.
        """
        in_flight: _InFlight | None = getattr(self._local, "in_flight", None)
        if in_flight is not None:
            in_flight.usage = usage

    def begin_call(self) -> _InFlight:
        in_flight = _InFlight()
        self._local.in_flight = in_flight
        return in_flight

    def end_call(self, call: LlmCallRecord) -> None:
        self._local.in_flight = None
        with self._lock:
            self.calls.append(call)

    def clear(self) -> None:
        with self._lock:
            self.calls.clear()

    def snapshot(self) -> list[LlmCallRecord]:
        """Copy sorted by start instant — insertion order reflects the *end* order
        of calls, which is meaningless under concurrency."""
        with self._lock:
            return sorted(self.calls, key=lambda call: call.started_at)


class TimedLLMClient:
    """Decorate an ``LLMClient``: time each call and record it.

    Transparent to the caller — ``complete`` returns the same ``str`` and
    lets exceptions through unchanged (an LLM error stays an LLM error;
    module 4.3 relies on the exact type to decide on a retry). A failing
    call is traced too, with ``ok=False``: it is precisely the case where
    we want to know how long it cost.
    """

    def __init__(
        self,
        inner: LLMClient,
        timeline: CallTimeline,
        *,
        phase: str,
        subject: CallSubject | None = None,
    ) -> None:
        self._inner = inner
        self._timeline = timeline
        self._phase = phase
        self._subject = subject

    def complete(self, prompt: str) -> str:
        in_flight = self._timeline.begin_call()
        started_at = datetime.now(tz=UTC)
        started = time.monotonic()
        error: str | None = None
        try:
            return self._inner.complete(prompt)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            usage = in_flight.usage
            self._timeline.end_call(
                LlmCallRecord(
                    phase=self._phase,
                    subject=self._subject,
                    started_at=started_at,
                    ended_at=datetime.now(tz=UTC),
                    duration_seconds=time.monotonic() - started,
                    ok=error is None,
                    error=error,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    cost_usd=usage.cost_usd if usage else None,
                )
            )
