# radar-automation

[![CI](https://github.com/nassim-systems/radar-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/nassim-systems/radar-automation/actions/workflows/ci.yml)

An automated monitoring pipeline: RSS feeds → LLM relevance scoring → draft posts.

What is worth reading here is not that it works. It is that every design decision is
measured before it is kept, including the decision to remove a component. The
measurements, and their limits, are in the repository.

## Read these first

| Document | What it shows |
|---|---|
| [`docs/QUALITY.md`](docs/QUALITY.md) | How the relevance threshold is calibrated: a hand-labelled real set, precision and recall per threshold, limits stated plainly. |
| [`docs/CRITIC_AGENT.md`](docs/CRITIC_AGENT.md) | A reviewer agent that was built, tested, measured and discarded: 67% false rejects on 14 real cases. |
| [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) | A timestamped trace per step, per article and per LLM call; what is measured and what is only a hypothesis. |

The other decision records: [`docs/WORKFLOW.md`](docs/WORKFLOW.md) (why explicit orchestration
rather than an agent), [`docs/ANGLE_AGENT.md`](docs/ANGLE_AGENT.md),
[`docs/CONCURRENCY.md`](docs/CONCURRENCY.md), [`docs/MIGRATION.md`](docs/MIGRATION.md),
[`docs/HELDOUT.md`](docs/HELDOUT.md). [`docs/DOSSIER_DEMO.md`](docs/DOSSIER_DEMO.md) is the ten-minute
version for a non-technical reader.

## The pipeline

```
fetch → deduplicate → filter_fresh → filter_unseen → score → filter_by_min_score
      → select_top_k → angle → write → mark_seen
```

Ten steps, three of which call a model (`score`, `angle`, `write`). The other seven are
deterministic, tested code: the sequence is fixed whatever the content, so there is no
reason to let a model decide the next step. Orchestration is explicit (`run_workflow`,
frozen Pydantic state), scoring runs concurrently under a hard budget with retry and
backoff, and every call is traced.

## Verifiable numbers

- **264 tests**, `ruff` clean.
- **`run_trace.json`**, one real run on 1 September 2026: 17 articles scored, 17 model
  calls, 0 failures, 3.8 s end to end for 13.4 s of cumulative call time (parallelism
  gain ×4.0), cost $0.008.
- **`docs/run_history.json`**, three real runs: 73 calls, 0 failures, about $0.040 in
  total.

## Limits, stated

- **Recall is 70% at the chosen threshold**: 3 relevant articles out of 10 are not
  processed that day. This is a documented choice in `QUALITY.md`: missing an article
  costs less than publishing a bad draft.
- **Samples are small** (n = 10 to 30 depending on the measurement). Trends are clear,
  confidence intervals are wide.
- **The system produces little**: two of the three recorded runs yielded no draft. It is
  a demanding filter, not a content machine.
- **Language**: the LLM prompts and the generated drafts are in French, and part of the
  evaluation data is French-language news, because the target audience is French-speaking
  SMBs. Documentation and code are in English.

## Run and reproduce

```bash
uv run ruff check . && uv run pytest -q     # 264 tests, no API key needed

export ANTHROPIC_API_KEY=...                # never in code, never in git
export FEED_URLS=https://example.com/feed,https://example.org/rss
uv run radar-run                            # writes run_report.json and run_trace.json
```

Daily scheduling (cron, Windows Task Scheduler) is described in
[`docs/scheduling.md`](docs/scheduling.md).

## Repository layout

```
src/         pipeline, workflow engine, drafting agents, observability
tests/       264 tests (no API key: the LLM layer is faked)
scripts/     calibration, held-out labelling, measurement and evaluation scripts
results/     raw outputs of the measurements cited in the decision records
docs/        decision records, demo dossier, scheduling guide, run history
run_trace.json, run_report.json    output of one real run
```

## A note on numbering

In documents and comments, "module 4.5" means a project step, numbered in the order it
was done: 1.x to 3.x cover the pipeline, the agent, observability and calibration; 4.x
are architecture trade-offs. Each 4.x trade-off and the calibration has its own document,
giving the question asked, the measurement and the decision.

## Stack

Python ≥ 3.11 · Pydantic · Anthropic SDK (Claude Haiku 4.5) · pytest · ruff.
