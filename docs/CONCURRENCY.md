# Parallelism, budgets & degradation (module 4.3)

[`radar/concurrent_scoring.py`](../src/radar/concurrent_scoring.py): bounded
concurrent scoring to replace the sequential loop of `ScoreStep`/
`run_pipeline` — without changing their output contract (same order, same
scores). Wired as `ConcurrentScoreStep`, a drop-in for `ScoreStep`, in
[`radar/workflow.py`](../src/radar/workflow.py).

## 1. Concurrent scoring, reassembled in input order

**Mechanism**: `ThreadPoolExecutor` (I/O-bound — LLM calls block on the
network, not on the CPU; no need for ``asyncio`` in this entirely synchronous
project). Items are processed in **batches** of at most
`max_concurrency`, each batch fully submitted and then awaited before moving
on to the next.

**Ordering guarantee**: each result is associated with the index of its
original item; the final list is explicitly sorted by this index before
being returned — regardless of the actual completion order. The decisive test
(`tests/test_concurrent_scoring.py::
test_concurrent_matches_sequential_under_variable_latency`) builds
deliberately inverted latencies (item 3 finishes before item 0) and checks
that the concurrent output is identical, item by item and in order, to the
sequential version (`score_item` in a loop). A second test
(`test_concurrent_preserves_input_order_across_multiple_batches`) checks the
same property across several batches.

## 2. Hard budget (`max_cost_usd`)

**Wired to the `UsageSink` of module 3.4**: before submitting each new
batch, the budget is checked via `usage_sink.total().cost_usd` — no cost
counting reinvented here.

**Chosen policy: clean truncation, never an exception.**
`ConcurrentScoreReport` returns the items scored successfully up to the
overrun, plus `n_skipped_budget` and `budget_exhausted=True` — the items not
attempted remain available for the next run (same semantics as
`unseen[:max_scored]`, which already truncates silently without raising).
Raising an error would lose all the work already paid for in the current run,
which no other truncation in this project does.

**Bounded overshoot, not unlimited.** The budget is only checked **between**
two batches — calls already in flight in a batch are never interrupted (no
clean cancellation of an in-progress HTTP request without disproportionate
complexity). The possible overshoot is therefore bounded to
`max_concurrency` calls, never unlimited. Tested:
`test_budget_truncates_cleanly_after_one_batch` (1 paid batch exceeds the
budget → the 2nd batch is never submitted) and `test_zero_budget_skips_
everything_without_any_call` (budget already reached from the start → no
call).

## 3. Controlled degradation: bounded retry + backoff

**Only transient errors are retried**: `TransientLLMError`
(`radar/llm/errors.py`), an SDK-neutral exception — `AnthropicClient`
translates the real `RateLimitError` (429) and `OverloadedError`
(529) errors into `TransientLLMError`; everything else (code bug, 400, auth...)
is never retried. Tested at the SDK level
(`tests/test_anthropic_client.py::
test_anthropic_client_translates_rate_limit_to_transient_error` and
`..._overloaded_...`, plus a negative test with `BadRequestError`) and at the
retry level (`tests/test_concurrent_scoring.py::
test_non_transient_error_is_never_retried`: zero retries, zero calls to
`sleep`).

**Scope deliberately restricted to 429/529** — a conscious exclusion, not an
oversight:
- `InternalServerError` (generic 5xx): often transient in practice, but not
  explicitly named in the request; easy to extend later if real experience
  justifies it.
- `APIConnectionError` (network drop): same, out of scope for this version.

**Capped exponential backoff** (`RetryPolicy`):
`base_delay_seconds * 2**retries`, bounded by `max_delay_seconds`.
`max_attempts` includes the initial attempt.

**Isolation, no batch abort.** An item that exhausts its retries (or fails
non-transiently) is counted in `n_failures` and excluded from
`scored` — the other items in the batch and in subsequent batches continue,
same policy as the existing drafting (`DraftStep`/`run_pipeline`): an
isolated LLM failure never brings down the whole run. Tested:
`test_exhausts_retries_and_isolates_as_failure_without_raising`,
invariant `n_attempted == len(scored) + n_failures`
(`test_n_attempted_equals_scored_plus_failures_invariant`).

## 4. Default decisions

| Parameter | Value | Justification |
|---|---|---|
| `max_concurrency` | **5** | No measurement of the real rate limit available (account/tier not observed in this project) — a prudent value: this radar already caps `max_scored=30` (module 1.x), so 5 gives a real gain (6 batches instead of 30 sequential calls) without risking saturating a modest API tier. Adjustable by the caller (`ConcurrentScoringConfig.max_concurrency`); to be adjusted if real 429s are observed in production. |
| `max_attempts` | **3** (1 try + 2 retries) | Enough to absorb a brief spike (rate limit, momentary overload) without making the pipeline wait indefinitely on a stuck item. |
| `base_delay_seconds` | **0.5 s** | Short initial delay — a 429/529 typically clears within a handful of seconds. |
| `max_delay_seconds` | **8 s** | Caps the exponential growth (0.5 → 1 → 2 → ... → 8) for a pipeline that stays time-bounded even under sustained degradation. |
| Budget policy | **Clean truncation** | See §2 — consistent with `max_scored`, no loss of work already paid for. |

## 5. Integration

`ConcurrentScoreStep` (`radar/workflow.py`) — same output contract as
`ScoreStep` (`state.scored`), bounded by `ConcurrentScoringConfig` in
addition to `PipelineConfig.max_scored` (unchanged, still the source of the
upstream truncation). Tested as a direct replacement in an existing list of
`Step`s, with a result identical to `ScoreStep` on `FakeLLM`
(`tests/test_radar_workflow_concurrent.py::
test_concurrent_score_step_is_a_drop_in_replacement_for_score_step`). At the
time of this module, not wired into `composition.py` — same scope as modules
4.1/4.2: a measured and tested capability, not a production migration unless
asked.

**Update (module 4.5, `MIGRATION.md`)**: `ConcurrentScoreStep` is now in
production, wired into `composition.py` via
`build_radar_steps_production`.

## Tests

- `tests/test_concurrent_scoring.py` (11 tests): sequential/parallel
  equivalence under variable latencies, concurrency bound actually observed
  (thread-safe counter), budget (zero, truncation, unlimited), retry
  (success after failures, isolated exhaustion, no retry on non-transient
  error), counting invariant.
- `tests/test_anthropic_client.py` (+3 tests): SDK → `TransientLLMError`
  translation for 429/529 only, not for 400.
- `tests/test_radar_workflow_concurrent.py` (2 tests): integration as a
  drop-in `Step`, `max_scored` respected.

```bash
uv run ruff check .
uv run pytest -q
```
