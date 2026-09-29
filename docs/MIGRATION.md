# Single production path (module 4.5)

## Decision

**Migration**: `composition.py::build_radar_pipeline` now wires
`radar/workflow.py::build_radar_steps_production` (fetch → dedup → fresh →
unseen → concurrent score → threshold → top-K → angle → write → mark_seen).
`run_pipeline` (module 1.x, a monolithic sequential function) is
**removed** from `radar/pipeline.py`. No third option retained: a single
production path now exists.

## 1. The two options, and why not deleting the workflow

This module imposed a binary choice: migrate to the workflow, or delete
`radar/workflow.py`/`core/workflow/` and keep `run_pipeline`.

**Deleting the workflow would also have deleted already-measured value**, not
just complexity:
- Module 4.1 proved strict Step/`run_pipeline` equivalence and per-step
  traceability that `run_pipeline` structurally cannot offer
  (`PipelineReport` only has aggregates).
- Module 4.2 **measured** (did not assume) that the AngleAgent +
  WriterAgent decomposition fixes a real defect of the single call — the
  forced SMB angle on an article that does not honestly offer one
  (`ANGLE_AGENT.md`). Keeping `run_pipeline` in production would have meant
  keeping this known defect, already fixed elsewhere in the repository,
  indefinitely.
- Module 4.3 delivered bounded, tested concurrent scoring (order
  equivalence under variable latencies, budget, retry) — a real latency gain
  on `max_scored=30`, which `run_pipeline` (strictly sequential) cannot
  offer.
- Module 4.4 measured and **rejected** the CriticAgent — so nothing to
  integrate on that side, but the measurement discipline applied to the
  three previous ones is exactly what makes the migration defensible: every
  retained component was retained on evidence, not on principle.

Deleting the workflow would therefore have thrown away three measured and
retained components in order to keep the only one that has **never**
integrated the module 4.2 fix. That is the decisive argument, not a
preference for "more code": the migration builds on decisions already made
and individually proven; deletion would have cancelled them without new
contrary evidence.

## 2. Dead path removed

- `radar/pipeline.py::run_pipeline` — removed. The module keeps only what
  the workflow reuses: `PipelineConfig`,
  `PipelineReport`, `ScoredDraft`, `filter_by_min_score`,
  `write_report_json`.
- `tests/test_pipeline.py` — reduced to tests of the surviving pure
  functions (`filter_by_min_score`, UTF-8 round-trip of
  `write_report_json`). The properties it verified for the complete pipeline
  (idempotence, budget, failure isolation, threshold) are re-demonstrated for
  the production composition in
  `tests/test_radar_workflow_production.py`.
- `tests/test_radar_workflow.py::test_radar_workflow_produces_same_drafts_as_run_pipeline`
  — its comparison target no longer exists; replaced by a test with frozen
  values (those that the equivalence had validated in 4.1), to keep this
  step of the migration under a safeguard without depending on a deleted
  function.

`build_radar_steps` (single call, sequential) and
`build_radar_steps_decomposed` (decomposed, sequential) **remain** in
`radar/workflow.py`, tested: they are not dead paths but alternative
compositions that demonstrate recomposition (see `WORKFLOW.md`) — the
distinction is that `composition.py` now wires only one of them for
production.

## 3. Rewiring (`composition.py`)

```diff
- from radar.pipeline import PipelineConfig, run_pipeline
+ from radar.concurrent_scoring import ConcurrentScoringConfig
+ from radar.pipeline import PipelineConfig
+ from radar.workflow import (
+     RadarWorkflowState,
+     build_radar_steps_production,
+     radar_workflow_state_to_pipeline_report,
+ )
+ from core.workflow.engine import run_workflow
```

```diff
      def run() -> RunRecord:
          usage_sink.calls.clear()
          config = PipelineConfig(...)
-        report = run_pipeline(
-            fetch_items=fetch_items, seen_store=seen_store, llm=llm, config=config
-        )
+        steps = build_radar_steps_production(
+            fetch_items=fetch_items, seen_store=seen_store, llm=llm,
+            config=config, concurrency_config=concurrency_config,
+            usage_sink=usage_sink,
+        )
+        workflow_run = run_workflow(steps, RadarWorkflowState(), usage_sink=usage_sink)
+        report = radar_workflow_state_to_pipeline_report(workflow_run.final_state)
          record = RunRecord(at=..., report=report, usage=usage_sink.total())
```

`usage_sink` is injected both into `AnthropicClient` **and** into
`build_radar_steps_production`/`run_workflow`: it is the same object in all
three places, a necessary condition for the hard budget of
`ConcurrentScoreStep` (module 4.3) to actually work (see
`CONCURRENCY.md`). `app.py` needs **no modification**: `run()`
still returns a `RunRecord(at, report: PipelineReport, usage: LlmUsage)`
— the contract consumed by `write_report_json`/`check_alert` is unchanged.

## 4. Production hardening

Two adjustments, necessary only because this path becomes the only
production path (not a bug fix, a robustness evolution justified by the
higher stakes):

- **`AngleStep` now isolates failures per item.** Before this module,
  an LLM error on the angle decision of a single item made the entire step
  fail — hence the entire run (`WorkflowError`, see
  `core/workflow/engine.py`). Acceptable for a one-off measurement (4.2), not
  for the only production path: `AngleStep` now follows the same policy as
  `ScoreStep`/`WriteStep` (per-item isolation, `n_failures` incremented, the
  item stays unseen). Tested:
  `tests/test_radar_workflow_production.py::
  test_angle_step_isolates_a_failing_item_instead_of_aborting_the_run`.
- **`n_llm_calls` rebuilt across the whole workflow.** Each step that
  calls an LLM (`ScoreStep`, `ConcurrentScoreStep`, `DraftStep`,
  `AngleStep`, `WriteStep`) now increments a counter carried by
  `RadarWorkflowState`, aggregated by `radar_workflow_state_to_pipeline_report`
  into the same `PipelineReport.n_llm_calls` field as before. For
  `ConcurrentScoreStep`, the count includes the real retries
  (`report.n_attempted + report.n_retries`) — more faithful to the number of
  API calls actually issued than the old `run_pipeline` counter, which did
  not know about retries (retry did not exist before 4.3).

## 5. Non-regression verified

- **`PipelineReport`**: schema unchanged (same fields, same types).
  `radar_workflow_state_to_pipeline_report` is its single source of truth
  for production. Tested:
  `test_radar_workflow_state_to_pipeline_report_maps_all_fields`.
- **`min_score = 8`**: unchanged in `composition.py`
  (`_MIN_SCORE = 8`, still calibrated per `QUALITY.md`). Tested
  end-to-end: `test_production_workflow_respects_min_score`.
- **Idempotence**: an item drafted successfully is marked seen; a skipped
  item (budget, threshold, angle absent, failure) stays unseen. Tested over
  two consecutive runs:
  `test_production_workflow_is_idempotent_across_two_runs`.
- **Complete `WorkflowRun`**: trace of the 10 steps with durations,
  aggregated usage, drafts in the final state — tested
  (`test_production_workflow_produces_a_complete_workflow_run`) and verified
  on a real run (§6).
- Full suite: `uv run pytest -q` → 235 passed. `uv run ruff check .`
  → clean.

## 6. Real verification run

Store emptied, real feeds (Zapier/n8n in addition to the existing general
feeds) to observe real end-to-end drafting through the new composition:

```
Report written to run_report.json (3 draft(s), 3 above threshold, 0.0214 USD).
```


`run_report.json` (`PipelineReport` schema unchanged): `n_fetched=57,
n_scored=30, n_above_threshold=3, n_drafted=3, n_llm_calls=36, n_failures=0`
— consistent (30 scoring + 3 angle + 3 write = 36). The 3 drafts (Claude ×
Zapier, AI website generators, Claude for small businesses) are natural, no
forced angle detected on review. `.data/run_history.json` correctly archived
the `RunRecord` after the existing history (module 3.4).

## Reproducibility

```bash
uv run ruff check .
uv run pytest -q
./check.sh
```
