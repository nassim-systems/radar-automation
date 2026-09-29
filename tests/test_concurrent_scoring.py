import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from core.usage import ListUsageSink, LlmUsage
from radar.concurrent_scoring import (
    ConcurrentScoringConfig,
    RetryPolicy,
    score_items_concurrently,
)
from radar.decision.models import ScoredItem
from radar.domain import RawItem
from radar.llm.errors import TransientLLMError
from radar.scoring import score_item

MAX_CONCURRENCY_BOUND = 3
N_ITEMS_FOR_BOUND_TEST = 9
CANNED_SCORE = 7


def _item(external_id: str, title: str) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        summary="résumé",
    )


def _recording_sleep() -> tuple[Callable[[float], None], list[float]]:
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)

    return sleep, calls


class _VariableLatencyLLM:
    """Different response and latency per item (key = title), to force a
    completion order that differs from the submission order; this is
    precisely what the final sort by index must correct."""

    def __init__(self, by_title: dict[str, tuple[str, float]]) -> None:
        self._by_title = by_title

    def complete(self, prompt: str) -> str:
        for title, (response, delay) in self._by_title.items():
            if title in prompt:
                time.sleep(delay)
                return response
        raise AssertionError(f"titre inattendu dans le prompt : {prompt[:200]}")


class _ConcurrencyTrackingLLM:
    """Count the number of calls actually in flight at the same time."""

    def __init__(self, hold_seconds: float) -> None:
        self._lock = threading.Lock()
        self._current = 0
        self.peak = 0
        self._hold = hold_seconds

    def complete(self, prompt: str) -> str:
        with self._lock:
            self._current += 1
            self.peak = max(self.peak, self._current)
        time.sleep(self._hold)
        with self._lock:
            self._current -= 1
        return "5"


class _FlakyLLM:
    """Fail with ``TransientLLMError`` the first N calls of this specific item
    (a single item in the tests that use it), then succeed."""

    def __init__(self, n_failures_before_success: int, canned: str) -> None:
        self._n_failures = n_failures_before_success
        self._canned = canned
        self._count = 0
        self._lock = threading.Lock()

    def complete(self, prompt: str) -> str:
        with self._lock:
            self._count += 1
            count = self._count
        if count <= self._n_failures:
            raise TransientLLMError("429 simulé")
        return self._canned


class _AlwaysNonTransientLLM:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("erreur non transitoire (ex. bug de code)")


class _UsageReportingLLM:
    """Simulate an ``AnthropicClient``: report a fixed cost per call."""

    def __init__(self, sink: ListUsageSink, canned: str, cost_per_call: float) -> None:
        self._sink = sink
        self._canned = canned
        self._cost = cost_per_call

    def complete(self, prompt: str) -> str:
        self._sink.record(
            LlmUsage(input_tokens=1, output_tokens=1, cost_usd=self._cost)
        )
        return self._canned


# --- 1. Proof of sequential/parallel equivalence, varied latencies ---


def test_concurrent_matches_sequential_under_variable_latency() -> None:
    by_title = {
        "Item0": ("1", 0.05),
        "Item1": ("2", 0.01),
        "Item2": ("3", 0.04),
        "Item3": ("4", 0.005),
        "Item4": ("5", 0.03),
    }
    items = [_item(str(i), f"Item{i}") for i in range(5)]

    seq_llm = _VariableLatencyLLM(by_title)
    sequential = [
        ScoredItem(item=item, score=score_item(item, seq_llm).score) for item in items
    ]

    report = score_items_concurrently(
        items,
        _VariableLatencyLLM(by_title),
        config=ConcurrentScoringConfig(max_concurrency=5),
    )

    # Same content AND same order, despite a scrambled completion order
    # par construction (Item3 finit en premier, Item0 en dernier).
    assert [(s.item.external_id, s.score) for s in report.scored] == [
        (s.item.external_id, s.score) for s in sequential
    ]


def test_concurrent_preserves_input_order_across_multiple_batches() -> None:
    # 7 items, max_concurrency=3 -> 3 batches; delays are chosen so that
    # each batch finishes in a different order than it was submitted.
    by_title = {f"Item{i}": (str(i), 0.05 - (i % 3) * 0.01) for i in range(7)}
    items = [_item(str(i), f"Item{i}") for i in range(7)]

    report = score_items_concurrently(
        items,
        _VariableLatencyLLM(by_title),
        config=ConcurrentScoringConfig(max_concurrency=3),
    )

    assert [s.item.external_id for s in report.scored] == [str(i) for i in range(7)]


# --- 2. Concurrency is actually bounded ---


def test_concurrency_never_exceeds_max_concurrency() -> None:
    llm = _ConcurrencyTrackingLLM(hold_seconds=0.03)
    items = [_item(str(i), f"Item{i}") for i in range(N_ITEMS_FOR_BOUND_TEST)]

    config = ConcurrentScoringConfig(max_concurrency=MAX_CONCURRENCY_BOUND)
    score_items_concurrently(items, llm, config=config)

    assert llm.peak == MAX_CONCURRENCY_BOUND


def test_max_concurrency_below_one_raises() -> None:
    with pytest.raises(ValueError):
        score_items_concurrently(
            [],
            _ConcurrencyTrackingLLM(0),
            config=ConcurrentScoringConfig(max_concurrency=0),
        )


# --- 3. Budget dur ---


def test_zero_budget_skips_everything_without_any_call() -> None:
    sink = ListUsageSink()
    llm = _UsageReportingLLM(sink, canned="7", cost_per_call=0.01)
    items = [_item(str(i), f"Item{i}") for i in range(3)]

    report = score_items_concurrently(
        items,
        llm,
        config=ConcurrentScoringConfig(max_concurrency=2, max_cost_usd=0.0),
        usage_sink=sink,
    )

    assert report.budget_exhausted is True
    assert report.n_attempted == 0
    assert report.n_skipped_budget == len(items)
    assert report.scored == []


def test_budget_truncates_cleanly_after_one_batch() -> None:
    n_items = 5
    n_first_batch = 2
    sink = ListUsageSink()
    llm = _UsageReportingLLM(sink, canned="7", cost_per_call=0.01)
    items = [_item(str(i), f"Item{i}") for i in range(n_items)]

    report = score_items_concurrently(
        items,
        llm,
        # 1st batch (2 calls) costs 0.02, already >= 0.015 -> the 2nd batch is
        # never submitted: clean truncation, no exception raised.
        config=ConcurrentScoringConfig(
            max_concurrency=n_first_batch, max_cost_usd=0.015
        ),
        usage_sink=sink,
    )

    assert report.budget_exhausted is True
    assert report.n_attempted == n_first_batch
    assert len(report.scored) == n_first_batch
    assert report.n_skipped_budget == n_items - n_first_batch
    assert [s.item.external_id for s in report.scored] == ["0", "1"]


def test_unset_budget_scores_everything() -> None:
    n_items = 3
    high_cost_no_cap = 1000.0
    sink = ListUsageSink()
    llm = _UsageReportingLLM(sink, canned="7", cost_per_call=high_cost_no_cap)
    items = [_item(str(i), f"Item{i}") for i in range(n_items)]

    report = score_items_concurrently(
        items, llm, config=ConcurrentScoringConfig(max_concurrency=2), usage_sink=sink
    )

    assert report.budget_exhausted is False
    assert len(report.scored) == n_items


# --- 4. Controlled degradation: bounded retry + backoff ---


def test_retries_transient_error_and_eventually_succeeds() -> None:
    expected_retries = 2
    llm = _FlakyLLM(
        n_failures_before_success=expected_retries, canned=str(CANNED_SCORE)
    )
    sleep, calls = _recording_sleep()
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=8.0)

    report = score_items_concurrently(
        [_item("1", "Alpha")],
        llm,
        config=ConcurrentScoringConfig(max_concurrency=1, retry=policy),
        sleep=sleep,
    )

    assert len(report.scored) == 1
    assert report.scored[0].score == CANNED_SCORE
    assert report.n_failures == 0
    assert report.n_retries == expected_retries
    assert calls == [0.5, 1.0]  # backoff exponentiel : 0.5 * 2**0, 0.5 * 2**1


def test_exhausts_retries_and_isolates_as_failure_without_raising() -> None:
    more_failures_than_max_attempts = 5
    llm = _FlakyLLM(
        n_failures_before_success=more_failures_than_max_attempts,
        canned=str(CANNED_SCORE),
    )
    sleep, calls = _recording_sleep()
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.1)

    report = score_items_concurrently(
        [_item("1", "Alpha")],
        llm,
        config=ConcurrentScoringConfig(max_concurrency=1, retry=policy),
        sleep=sleep,
    )

    expected_retries = policy.max_attempts - 1
    assert report.scored == []
    assert report.n_failures == 1
    assert report.n_retries == expected_retries
    assert len(calls) == expected_retries


def test_non_transient_error_is_never_retried() -> None:
    sleep, calls = _recording_sleep()

    report = score_items_concurrently(
        [_item("1", "Alpha")],
        _AlwaysNonTransientLLM(),
        config=ConcurrentScoringConfig(max_concurrency=1),
        sleep=sleep,
    )

    assert report.scored == []
    assert report.n_failures == 1
    assert report.n_retries == 0
    assert calls == []  # never any backoff for a programming error


def test_n_attempted_equals_scored_plus_failures_invariant() -> None:
    llm = _FlakyLLM(n_failures_before_success=1, canned="7")
    sleep, _ = _recording_sleep()
    items = [_item(str(i), f"Item{i}") for i in range(4)]

    report = score_items_concurrently(
        items, llm, config=ConcurrentScoringConfig(max_concurrency=2), sleep=sleep
    )

    assert report.n_attempted == len(report.scored) + report.n_failures
