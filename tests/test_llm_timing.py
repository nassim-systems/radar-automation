"""Instrumentation temporelle des appels LLM (module 4.6, OBSERVABILITY.md).

Ce que ces tests garantissent : le décorateur est *transparent* (même sortie,
mêmes exceptions), il attribue chaque appel à son item et à sa phase, et
l'attribution de l'usage reste correcte quand plusieurs appels s'exécutent
en parallèle — le seul point de ce module où une erreur serait silencieuse.
"""
import threading
import time

import pytest

from core.usage import ListUsageSink, LlmUsage, TeeUsageSink
from radar.llm.fake import FakeLLM
from radar.llm.timing import CallSubject, CallTimeline, TimedLLMClient

SUBJECT = CallSubject(key="rss:1", title="Un titre", url="https://x.example/1")
CALL_COST_USD = 0.004
INPUT_TOKENS = 10
N_CONCURRENT_ITEMS = 6


class _UsageEmittingLLM:
    """Imite ``AnthropicClient`` : notifie son sink *pendant* l'appel."""

    def __init__(self, sink: TeeUsageSink, cost: float, delay: float = 0.0) -> None:
        self._sink = sink
        self._cost = cost
        self._delay = delay

    def complete(self, prompt: str) -> str:
        time.sleep(self._delay)
        self._sink.record(
            LlmUsage(input_tokens=10, output_tokens=2, cost_usd=self._cost)
        )
        return "8"


def test_timed_client_is_transparent_and_records_phase_and_subject() -> None:
    timeline = CallTimeline()
    client = TimedLLMClient(
        FakeLLM("8"), timeline, phase="score", subject=SUBJECT
    )

    assert client.complete("prompt") == "8"  # sortie inchangée

    (call,) = timeline.snapshot()
    assert call.phase == "score"
    assert call.subject is not None
    assert call.subject.key == "rss:1"
    assert call.ok is True
    assert call.error is None
    assert call.duration_seconds >= 0
    assert call.started_at <= call.ended_at


def test_failing_call_is_recorded_and_the_exception_still_propagates() -> None:
    class _Boom:
        def complete(self, prompt: str) -> str:
            raise RuntimeError("panne LLM")

    timeline = CallTimeline()
    client = TimedLLMClient(_Boom(), timeline, phase="write", subject=SUBJECT)

    with pytest.raises(RuntimeError, match="panne LLM"):
        client.complete("prompt")

    (call,) = timeline.snapshot()
    assert call.ok is False
    assert "RuntimeError" in (call.error or "")
    assert call.phase == "write"
    # Un appel raté a quand même coûté du temps : c'est justement le cas
    # qu'on veut pouvoir chiffrer.
    assert call.duration_seconds >= 0


def test_usage_is_attributed_to_the_call_that_produced_it() -> None:
    timeline = CallTimeline()
    list_sink = ListUsageSink()
    tee = TeeUsageSink([list_sink, timeline])
    client = TimedLLMClient(
        _UsageEmittingLLM(tee, cost=CALL_COST_USD),
        timeline,
        phase="score",
        subject=SUBJECT,
    )

    client.complete("prompt")

    (call,) = timeline.snapshot()
    assert call.cost_usd == CALL_COST_USD
    assert call.input_tokens == INPUT_TOKENS
    # Le sink historique reçoit exactement le même usage : un seul comptage.
    assert list_sink.total().cost_usd == CALL_COST_USD


def test_usage_recorded_outside_any_call_is_dropped_not_misattributed() -> None:
    timeline = CallTimeline()
    timeline.record(LlmUsage(input_tokens=99, output_tokens=99, cost_usd=9.0))
    client = TimedLLMClient(FakeLLM("8"), timeline, phase="score", subject=SUBJECT)

    client.complete("prompt")

    (call,) = timeline.snapshot()
    assert call.cost_usd is None  # mieux qu'un chiffre faux


def test_attribution_stays_correct_across_concurrent_calls() -> None:
    """Le point critique : chaque thread doit attribuer SON usage à SON appel.

    Les coûts sont distincts par item et les latences volontairement
    inversées (le dernier item est le plus rapide) — si l'attribution passait
    par un état partagé, les coûts se mélangeraient.
    """
    timeline = CallTimeline()
    tee = TeeUsageSink([ListUsageSink(), timeline])
    n_items = N_CONCURRENT_ITEMS

    def call(index: int) -> None:
        client = TimedLLMClient(
            _UsageEmittingLLM(tee, cost=index / 1000, delay=(n_items - index) / 100),
            timeline,
            phase="score",
            subject=CallSubject(key=f"rss:{index}", title=f"Titre {index}"),
        )
        client.complete("prompt")

    threads = [threading.Thread(target=call, args=(i,)) for i in range(n_items)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    calls = timeline.snapshot()
    assert len(calls) == n_items
    by_key = {c.subject.key: c.cost_usd for c in calls if c.subject is not None}
    assert by_key == {f"rss:{i}": i / 1000 for i in range(n_items)}


def test_clear_resets_the_timeline_between_runs() -> None:
    timeline = CallTimeline()
    TimedLLMClient(FakeLLM("8"), timeline, phase="score").complete("p")
    assert len(timeline.snapshot()) == 1

    timeline.clear()

    assert timeline.snapshot() == []
