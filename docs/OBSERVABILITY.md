# Trace, latencies and human value (module 4.6)

## Decision

**Kept, with a clear boundary between what is measured and what is
assumed.** Three building blocks delivered:

1. **Exportable timestamped trace** — every step, every item and every LLM
   call of a run, in `run_trace.json`.
2. **Latencies** — per call, per item, per phase, per step, and end to end,
   with the concurrency gain measured rather than claimed.
3. **Human-value equation** — human time replaced, equivalent cost, ROI
   projection, **explicitly parametric** until a real timing has taken place.

The third is not of the same nature as the first two, and the code says so:
`HumanBaseline.measured` distinguishes an assumption from a measurement. This
is the structuring decision of this module.

## 1. Context

Modules 4.1 to 4.5 produced real observability — duration per step
(`WorkflowRun.trace`), tokens and cost (`UsageSink`) — but **none of it left
the process**. `run_report.json` only contains aggregate counters; this is
exactly the gap diagnosed in module 3.5 (`QUALITY.md` §4: "the exact batch of
the run was not kept… impossible to reconstruct after the fact").
Auditability was a property of the engine, not a consultable artefact.

Second gap, more embarrassing: **no latency anywhere**. The project measures
its precision and its cost to the thousandth of a dollar, and cannot say how
long a run takes.

Third gap, of a different nature: the cost of a run (0.0214 USD) is an
orphan figure. Cheap **compared to what**? Without a human point of
comparison, it demonstrates nothing.

## 2. Architecture decisions

### 2.1 A separate artefact, not an enlarged `PipelineReport`

**Decision: `run_trace.json`, paired with `run_report.json` by `run_at`.**

`MIGRATION.md` §5 sets an explicit non-regression — the `PipelineReport`
schema is unchanged — and that is what made the module 4.5 migration
verifiable. `RunRecord` (hence `run_history.json`, with two runs already
archived) depends on it directly. Grafting the trace onto it would break that
guarantee for a purely cosmetic reason.

Accepted cost: two files to read instead of one. In exchange, one more
contract, no broken contract, and a `run_trace.json` that nothing forces you
to produce — a caller who only wants the report pays nothing.

Drafts are **not** duplicated in the trace: they live in `run_report.json`.
Two copies to keep consistent for zero new information is the kind of
duplication this project refuses elsewhere.

### 2.2 An `LLMClient` decorator, not a modified `AnthropicClient`

**Decision: `TimedLLMClient` decorates any `LLMClient`.**

Same reasoning as for the `UsageSink` of module 3.4: the real client does not
need to know about observability. Useful consequence: the `FakeLLM` /
`ScriptedFakeLLM` of the tests can be instrumented exactly like the
production client — all the trace tests run without an API key.

**Explicit attribution, not guessed.** The decorator carries the call's
*subject* (the item) and its *phase* (the step name): each step creates one
decorator per item. Nothing is reconstructed after the fact by temporal
correlation, which would be wrong as soon as there is concurrency.

**The phase name is the step name, by construction.** This is what allows the
*cumulative* time of a phase's calls to be compared with the *actual* time of
the corresponding step — and thus the concurrency gain (§3.2) to be measured
rather than claimed.

### 2.3 Usage attribution: thread-local, by design

**Decision: `CallTimeline` implements `UsageSink` and attributes the received
usage to the call in progress in the current thread, via `TeeUsageSink`.**

This is the only delicate point of the module, hence the most tested. The
correctness rests on a precise property: `AnthropicClient.complete` notifies
its sink **synchronously, in the thread that executes the call** — the same
one as the decorator's, including in the `ThreadPoolExecutor` of concurrent
scoring (module 4.3). A dedicated test verifies it with six parallel calls
with distinct costs and deliberately inverted latencies: if attribution went
through shared state, the costs would get mixed up
(`tests/test_llm_timing.py::test_attribution_stays_correct_across_concurrent_calls`).

**No counting reinvented**: the source remains the usage returned by the SDK.
`TeeUsageSink` broadcasts the same object to the `ListUsageSink` (hard
budget, `RunRecord` total) and to the timeline (per-call attribution) — two
consumers, one source, not two counts that could diverge.

**Safe default**: a usage received outside any instrumented call is
**ignored**, not attributed at random. A missing field is better than a wrong
figure — same asymmetry as the fail-closed of the `CriticAgent`
(`CRITIC_AGENT.md` §2).

### 2.4 Strictly optional instrumentation

`timeline=None` everywhere by default. No step takes a different code path
depending on whether it is instrumented: either the decorator is applied or
the identity is. **Proof**: the 235 tests from before this module pass
without modification after the instrumentation is added. The only tests
touched (`test_entrypoint.py`) are touched because the runner now returns two
objects — not because a behaviour changed.

### 2.5 The runner measures, the entry point interprets

**Decision: the value equation is applied in `app.py`, not in
`composition.py`.**

The trace is a measurement; the equation rests on **business assumptions**
(hourly cost, triage time, runs per month). Mixing them in the same layer
would make it impossible to say which of the two figures is observed.
`composition.py` therefore produces a trace without the equation, and
`app.py` applies to it the baseline loaded from `human_baseline.json` —
absent by default, in which case the default assumptions are used **and
flagged** (`value.baseline.measured = false`).

## 3. What the trace actually provides

### 3.1 Two independent counters that must coincide

`counters.n_llm_calls` is reconstructed by the steps (module 4.5, retries
included); `n_llm_calls_traced` is the number of records actually produced by
the calls. The two are obtained by **distinct** paths — which is precisely
what makes a discrepancy visible if one appears. A run where they diverge is
a bug, not an acceptable variant.

### 3.2 The concurrency gain, measured

`PhaseTiming.speedup` = cumulative time of a phase's calls ÷ actual time of
the homonymous step. At 1.0 the step is sequential; above it, the step
overlaps its calls. On a demonstration run with 6 items and 5 concurrent
calls (fake LLM with fixed latency, `max_concurrency=5`):

| Phase | Calls | Cumulative | Actual (step) | Speedup |
|---|---|---|---|---|
| `score` | 6 | 0.901 s | 0.302 s | **2.98** |
| `angle` | 3 | 0.451 s | 0.451 s | 1.00 |
| `write` | 3 | 0.451 s | 0.451 s | 1.00 |

This is the first **end-to-end** verification of the module 4.3 promise:
scoring does overlap its calls, while angle and writing remain sequential —
which is the intended behaviour, not a defect.

> **These figures come from a fake LLM**, not a real run: they validate the
> measurement mechanics, not production latency. The first real run with
> `run_trace.json` will replace this table.

### 3.3 The orchestration cost, kept visible

`latency.orchestration_seconds` is the gap between the actual duration of the
run and the sum of the steps. Keeping it explicit avoids the common
temptation to present the sum of the steps as the run duration. On the
demonstration above: 0.1 ms out of 1.2 s — the engine costs nothing, but it
is now a measurement, not an intuition.

## 4. The value equation — scope and honesty

Everything else in this project is measured: scores come from a hand-labelled
held-out, costs from the SDK, latencies from a clock. **Here, not.** A value
equation rests on human parameters that this repository cannot measure on its
own.

The separation is embodied in the type: `HumanBaseline` carries the
assumptions, `ValueEquation` carries the computation, and
`ValueEquation.baseline` embeds the parameters with the result — an ROI
figure separated from its assumptions is uninterpretable and, worse, reusable
out of context.

**The term that prevents overestimation.** `seconds_per_draft_review`: the
system does not remove human work, it moves it. A produced draft must still
be reviewed and validated, and this residual time is **deducted** from the
gain. Without this term, the equation would systematically overestimate —
this is the standard error of all automation ROI calculators, and it is
avoided here by construction, not by vigilance.

**Non-computable ratios.** `roi_ratio` and `time_compression_ratio` are
`None` rather than infinity when their denominator is zero. An undefined
ratio must not present itself as a very large number.

**The equation follows actual production**, not a theoretical capacity: a run
that drafts nothing produces a zero drafting gain. Since the real runs of
3.3, 3.4 and 3.5 all drafted 0 items, this case is not hypothetical.

**What this equation will never prove**, even timed: that the human work
replaced had value. It quantifies time avoided, not a benefit obtained. The
distinction must remain explicit everywhere these figures are presented.

### Moving from assumption to measurement

`scripts/measure_human_baseline.py` times the triage on the **real items of
the last run** (read from `run_trace.json`, not examples chosen for the
exercise), then the writing and the review, and writes `human_baseline.json`
with `measured=true`. Accepted limit, identical to that of `QUALITY.md` and
`ANGLE_AGENT.md`: a single annotator, a single pass.

## 5. Scope (honest)

- **No real run has produced a `run_trace.json` yet.** The mechanics are
  tested end to end with fake LLMs; production latencies remain unknown until
  the next run with an API key.
- **The measured latencies include network and service**, without
  distinguishing them: `duration_seconds` is the time seen by the caller, not
  the model's compute time. It is the right measure for sizing a run, not for
  diagnosing slowness on the provider side.
- **The default budget of `HumanBaseline` is not a disguised measurement**
  (25 s of triage, 8 min of writing, 45 s of review, €50/h): these are orders
  of magnitude chosen to be replaced.
- **`speedup` compares a phase to a homonymous step.** A phase with no
  corresponding step reports no speedup rather than an invented ratio.

## 6. Tests

- `tests/test_llm_timing.py` (6): decorator transparency, failed call traced
  and exception propagated, usage attribution, usage outside a call ignored,
  **correct attribution under concurrency**, reset.
- `tests/test_run_trace.py` (8): speedup, no speedup without a step,
  per-item aggregation, calls without a subject excluded, full production run
  (phases, items, coincidence of the two counters), latencies and timestamps,
  UTF-8 round-trip, empty run with no invented ratio.
- `tests/test_value_equation.py` (8): arithmetic, review deduction, monthly
  projection, run without a draft, `None` ratios, default baseline flagged as
  not measured, disk round-trip.
- `tests/test_workflow_engine.py` (+): step timestamps, order, run duration ≥
  sum of steps, failed step timestamped.
- `tests/test_entrypoint.py` (+): two distinct artefacts, `run_report.json`
  with no trace field, equation present and flagged as not measured.

Full suite at delivery of this module: **258 passed** (235 before). `ruff check .` clean.

## Reproducibility

```bash
uv run ruff check . && uv run pytest -q     # definition of done (CLAUDE.md)
uv run radar-run                            # writes run_report.json AND run_trace.json
uv run python scripts/measure_human_baseline.py   # replaces the assumptions with a measurement
```
