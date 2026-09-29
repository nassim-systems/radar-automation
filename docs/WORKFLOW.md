# Workflow — architecture trade-off & orchestration (module 4.1)

## 1. Trade-off grid: deterministic flow / orchestration / agents

Three ways to chain steps, with a single selection criterion: **is the
sequence of steps known in advance, or decided dynamically by a model based
on the content?**

| | Sequence | Who decides "next step" | Cost/latency | Auditability |
|---|---|---|---|---|
| **Deterministic flow** (function, e.g. the current `run_pipeline`) | Fixed, hard-coded | Nobody — it is the code | Minimal | The code IS the trace; nothing observable at runtime without manual instrumentation |
| **Explicit orchestration** (`Step` / `run_workflow`, this module) | Fixed, but reified into objects | Nobody — still coded, just composed | Minimal (same work, just structured) | *Free* per-step trace: name, duration, success/failure, usage |
| **Agents** (LLM chooses the next action, e.g. ReAct loop) | Dynamic, depends on content | The model, at every turn | High (LLM calls to DECIDE, not only to EXECUTE) | Low by default — every decision must be logged to reconstruct it |

**Verdict for the radar**: the pipeline (fetch → dedup → fresh → unseen →
score → filter → top-k → draft) has a **strictly fixed** sequence,
whatever the content of the articles. Nothing in this pipeline justifies an
LLM deciding "and now, which step?" — that question has a static answer.
An agent would add latency, cost and non-determinism for zero benefit:
**explicit orchestration is the right level**, neither a frozen flow that is
unreadable at observation time, nor agent complexity that nothing justifies.

The same criterion applies to `handle_message` (module 2.5): its chain
(`classify` → load conversation → route the read tools → `draft_reply` →
propose the action) is *also* a fixed sequence — it is a **hard-coded
structured routing** (`_ROUTES` in `agent/agent/runner.py`), not an agentic
loop. It is therefore, by construction, a candidate for the same reification
— not done in this module (scope: a single real workflow, see §3), but the
generality of the abstraction can be verified by inspection: the shape is
identical (fixed sequence, state enriched at each step).

## 2. Architecture decisions

### 2.1 Typing of `WorkflowState`

**Decision: neither purely "typed per workflow" nor purely "generic" — a
generic engine, concrete states typed by subclassing.**

`core/workflow/models.py::WorkflowState` is a near-empty Pydantic base
(`frozen=True` only). `core/workflow/engine.py::Step`/`run_workflow`
are written against this base — a single engine, reusable by any workflow.
Each concrete workflow (e.g. `radar/workflow.py::
RadarWorkflowState`) defines its own subclass with typed fields
(`items: list[RawItem]`, `scored: list[ScoredItem]`...) — as
`PipelineReport`, `RunRecord`, `AgentResult` already do everywhere else in
this project. No generic bag (`data: dict[str, Any]`): that would be the
only real regression compared to the existing code, where *all* business
state is a typed Pydantic model.

**Why not full genericity (`Step[S]`/`WorkflowRun[S]` with
`TypeVar`)**: this project does not run mypy (`check.sh` = `ruff + pytest`) —
parameterizing the types with `Generic[S]` would add `typing` machinery that
nothing in CI checks. Instead, each concrete step explicitly narrows the
state via `_as_radar_state()` (a plain `isinstance` + `TypeError` with a
clear message) — the safety cost sacrificed by giving up static generics is
repaid by an *explicit, immediate* error if a step receives the wrong state,
rather than a confusing `AttributeError` further down. This is the same
choice as the rest of the project: prefer a clear runtime error to a static
guarantee that is not verified in practice.

**Accepted cost**: each new workflow defines its own state subclass
(verbose). This is a deliberate trade-off, not an oversight — consistent with
the "no duplication, no generic bag" discipline already in place everywhere
in this project.

### 2.2 Step error handling: abort, not skip, no compensation

**Decision: a step that raises interrupts the whole run (`WorkflowError`,
partial trace + usage attached). No "step skip". No compensation.**

- **No step skip.** Unlike an item within a batch (where "skipping" a
  failing item and continuing with the others makes sense — see
  `run_pipeline`, item-by-item isolation of LLM failures), a workflow
  **step** is a complete unit of work on which all subsequent steps depend
  (`score` needs `unseen`, `draft` needs `top_k`...). Silently skipping it
  would break what follows in unpredictable ways — worse than a clean abort.
- **Fine-grained resilience stays INSIDE the step, not in the orchestrator.**
  `DraftStep` (radar/workflow.py) still isolates LLM failures item by item
  internally (`try/except` around `llm.complete`, exactly as
  `run_pipeline` already does) — it is the same policy as before, inside
  the step. `run_workflow` only catches what *escapes* a step: a real bug or
  an unhandled outage. Consistent with the rule already applied everywhere
  else in this project (scoring, drafting, RSS fetch): *known and expected*
  failures are isolated locally; a code bug propagates.
- **No compensation (saga/rollback).** No step in the radar workflow has a
  side effect to undo in the saga sense: the only side effects
  (`mark_seen`) are deliberately placed in the very last step, after
  everything else has succeeded — if it fails, there is nothing to
  compensate upstream (no previous write). Adding compensation machinery now
  would be complexity without a real use case (YAGNI); to be reconsidered if
  a future workflow interleaves steps with side effects.

### 2.3 Observability: reuse the `UsageSink` from 3.4, do not reinvent it

**Decision: `run_workflow` knows nothing about tokens/costs — it delegates
entirely to the `ListUsageSink` of module 3.4.**

`WorkflowRun.usage` is populated by calling `sink.total()` once the run has
finished (or at the time of failure, for the `WorkflowError`); the sink
itself is the same object as the one injected into `AnthropicClient`
(module 3.4) — the steps that make LLM calls (`ScoreStep`, `DraftStep`) do so
through an already-instrumented `LLMClient`, exactly as `composition.py`
wires it for `run_pipeline`. **No token/cost counting code exists in
`core/workflow/`.**

**What IS new** (deliberately, as it is not covered by 3.4): the per-step
duration (`StepTrace.duration_seconds`, measured with
`time.monotonic()`). The LLM usage sink was never meant to measure generic
execution time — it is an orchestration concern, not an LLM billing one. The
distinction is deliberate: reuse what already exists (cost/tokens), add only
what is genuinely missing (per-step timing) and only makes sense at the
orchestrator level.

**Move `radar/llm/usage.py` → `core/usage.py`.** Necessary so that
`core/workflow/` (generic, with no dependency on `radar` or `agent`) can
reuse `LlmUsage`/`ListUsageSink` without inverting the direction of
dependencies (`core` is the foundation; `radar`/`agent`/`executor` build on
it, never the reverse — see `core/sanitize.py`, already shared by both). The
module itself had no internal dependency on `radar` (just
`pydantic`/`typing`) — the move is mechanical, zero behavior change, all
callers updated and tested.

## 3. Real use case: the radar pipeline as a workflow

[`src/radar/workflow.py`](../src/radar/workflow.py) breaks `run_pipeline` down
into **9 `Step`s**: `fetch`, `deduplicate`, `filter_fresh`, `filter_unseen`,
`score`, `filter_by_min_score`, `select_top_k`, `draft`, `mark_seen`. Each
step **delegates** to the pure function that `run_pipeline` already uses
(`deduplicate`, `filter_fresh`, `score_item`, `filter_by_min_score`,
`select_top_k`, `build_draft_prompt`/`parse_draft`) — **zero duplicated
logic**. `run_pipeline` was neither touched nor removed from production
(`composition.py::build_radar_pipeline` keeps using it as is): this module
adds a second path, it removes none.

### Proof that this is not a cosmetic rewrite

1. **Numerical equivalence tested**
   (`tests/test_radar_workflow.py::test_radar_workflow_produces_same_drafts_as_run_pipeline`):
   same items, same `FakeLLM`, same `PipelineConfig` → the workflow and
   `run_pipeline` produce exactly the same drafts, scores and counters. If
   they diverged, that would be a bug — not an acceptable variant.
2. **Traceability that `run_pipeline` does not offer.** `PipelineReport` only
   has aggregate counters (`n_scored`, `n_drafted`...) — no idea of the time
   spent in each stage, nor of which step failed, if any.
   `WorkflowRun.trace` gives both, for free, for any workflow built with this
   engine (`tests/test_radar_workflow.py::
   test_radar_workflow_trace_has_one_entry_per_step_all_successful`).
   This is directly what was missing during the module 3.5 diagnosis:
   without the list of items per stage, it was impossible to know afterwards
   which run had produced what (see `QUALITY.md`, point 4).
3. **Recomposition without code duplication**
   (`tests/test_radar_workflow.py::test_radar_workflow_recomposes_a_scoring_only_dry_run`):
   a "scoring only" dry-run (without `draft` or `mark_seen`, hence with no
   drafting LLM call and no side effect on the seen-store) is obtained by
   **filtering the `Step` list** — no function to copy-paste, no
   `dry_run: bool` parameter to thread through `run_pipeline`. This is
   exactly the kind of variant that a hard-coded flow does not allow without
   editing it.
4. **Observable abort, not a bare exception.** If `fetch` fails,
   `run_pipeline` raises a raw exception and loses all context about what had
   already run. `run_workflow` raises `WorkflowError` with the partial trace
   and the usage already accumulated attached
   (`tests/test_radar_workflow.py::test_radar_workflow_aborts_with_partial_trace_when_fetch_fails`).

### Scope deliberately not covered by this module

- `composition.py::build_radar_pipeline` is **not** migrated to this
  workflow — `run_pipeline` remains the production path. Since the
  decomposition into `Step`s is strictly equivalent (proven in §3.1),
  migrating would be a low-risk change, but it was not requested; leaving it
  as is avoids touching an already calibrated production path (module 3.5)
  without need.
- `handle_message` is not rewritten as a workflow (see §1) — out of scope for
  this module ("at least one real workflow"), but its shape would lend itself
  to it in the same way.

> **Update (module 4.5, see `MIGRATION.md`)**: the migration initially
> deferred above has taken place. `run_pipeline` has been **removed** —
> `composition.py::build_radar_pipeline` now wires
> `build_radar_steps_production` (concurrent scoring + decomposed drafting).
> It is precisely the equivalence proven in this document that made the
> migration safe.

## Tests

- `tests/test_workflow_engine.py`: isolated generic engine (dummy state,
  no radar dependency) — immutability, state-threading order, trace, usage
  capture, abort + error enrichment.
- `tests/test_radar_workflow.py`: real use case — order of the 9 steps,
  equivalence with `run_pipeline`, idempotence of `mark_seen`, complete
  trace, usage capture across `score`+`draft`, abort on fetch failure,
  dry-run recomposition.

```bash
uv run ruff check .
uv run pytest -q
```
