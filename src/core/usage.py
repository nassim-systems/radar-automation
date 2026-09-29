from typing import Protocol

from pydantic import BaseModel


class LlmUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class UsageSink(Protocol):
    """Separate channel for LLM usage.

    ``AnthropicClient.complete`` keeps returning a ``str`` (none of the many
    existing callers — scoring, drafting, agent — needs to change); if a sink
    is injected, it is notified after each real call.
    """

    def record(self, usage: LlmUsage) -> None: ...


class ListUsageSink:
    """Accumulate usages in memory and expose their sum.

    Same spirit as ``RecordingActionSink`` (module 3.1): a simple sink for
    the composition root and tests.
    """

    def __init__(self) -> None:
        self.calls: list[LlmUsage] = []

    def record(self, usage: LlmUsage) -> None:
        self.calls.append(usage)

    def total(self) -> LlmUsage:
        return LlmUsage(
            input_tokens=sum(u.input_tokens for u in self.calls),
            output_tokens=sum(u.output_tokens for u in self.calls),
            cost_usd=sum(u.cost_usd for u in self.calls),
        )


class TeeUsageSink:
    """Broadcast each usage to several sinks, in the given order.

    Needed since module 4.6 (``OBSERVABILITY.md``): the hard budget of
    concurrent scoring reads the aggregated total of a ``ListUsageSink``
    (module 4.3) while the call timeline attributes the same usage to the
    LLM call in progress. Two consumers, one source — rather than two
    parallel counts that could diverge.

    No policy of its own: no filtering, no transformation, no error
    swallowing. If a sink raises, the error propagates (a broken sink is a
    bug, not an incident to swallow).
    """

    def __init__(self, sinks: list[UsageSink]) -> None:
        self._sinks = sinks

    def record(self, usage: LlmUsage) -> None:
        for sink in self._sinks:
            sink.record(usage)
