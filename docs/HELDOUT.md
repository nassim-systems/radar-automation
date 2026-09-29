# Out-of-sample evaluation (held-out)

## Claim

The SMB relevance scorer, evaluated **out-of-sample** on **15 articles from a
source never seen in training** (Numerama — frozen, hand-labelled
held-out), obtains an **agreement of 0.93** and a **Spearman rank
correlation of 0.87** with the human labels.

## Metrics

| Metric | Value | n |
|---|---|---|
| Agreement (`1 − MAE/10`) | **0.9333** | 15 |
| Spearman (rank correlation) | **0.8693** | 15 |

## Scope (honest)

This held-out is **dominated by irrelevant content** (tech / general news) —
labels mostly 0-2. The metric therefore mainly validates the scorer's
**specificity**:

- it **does not over-score off-topic content** (the 8 clearly off-topic items
  → `human_label = 0`, `model_score = 0`);
- it **preserves the ranking** of the few slightly more relevant items.

It **does not yet demonstrate** the scorer's ability to **finely discriminate
true SMB positives**: that would require a held-out richer in relevant items
(lead "expand the held-out with true positives and edge cases").

**Follow-up (module 3.5)**: [`QUALITY.md`](QUALITY.md) fills this gap with a
second held-out, built this time to cover the three relevance tiers
(off-topic / medium / highly relevant), and uses it to calibrate `min_score`
by precision/recall rather than by gut feeling.

## Reproducibility

- Frozen, labelled set: [`src/radar/eval/heldout_labeled.json`](../src/radar/eval/heldout_labeled.json)
  (15 `RawItem + label` items, validated human labels).
- Recomputation (real LLM calls, outside the test suite):

  ```bash
  uv run python scripts/eval_heldout.py
  ```

  Writes the per-item detail (`human_label` / `model_score`) and the metrics
  to `heldout.json`.
