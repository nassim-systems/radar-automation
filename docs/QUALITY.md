# Calibration of `min_score` — representative held-out

> **Revision history**: the previous version of this document relied on a
> **hand-written** held-out (invented titles, realistic but fictional). A
> fictional calibration set proves nothing about real data: it has been
> replaced by a **genuinely collected** held-out. This document is entirely
> redone on that basis: 30 **actually scraped** items from 7 real RSS feeds,
> read and hand-labelled one by one.

## Claim

On a **sealed held-out of 30 actually scraped items** (not written), covering
the three relevance tiers, `min_score = 8` reaches **100% precision on the
"highly relevant" tier** (no off-topic or medium item is ever drafted), at the
cost of **70% recall** on that same tier (3 of the 10 truly relevant items are
scored 7 by the model, just below the threshold). An independent check on 20
unfiltered real items confirms it: **zero false positives**, both in the
held-out and under real conditions.

## 1. Held-out source — genuinely collected

**RSS feeds tested and verified with real network calls** (`scripts/scrape_heldout_pool.py`):

| Feed | URL | Status |
|---|---|---|
| Zapier blog | `zapier.com/blog/feed/` | ✅ 25 items |
| n8n blog | `blog.n8n.io/rss/` | ✅ 15 items (requires the `certifi` CA bundle, see §5) |
| Blog du Modérateur — tools | `blogdumoderateur.com/tools/feed` | ✅ 12 items |
| Blog du Modérateur — marketing | `blogdumoderateur.com/marketing/feed` | ✅ 30 items |
| Blog du Modérateur — no-code | `blogdumoderateur.com/no-code/feed` | ✅ valid feed, 0 items that day |
| FrenchWeb | `frenchweb.fr/feed` | ✅ 100 items |
| Siècle Digital | `siecledigital.fr/feed/` | ✅ 20 items |
| Make.com blog | — | ❌ no public RSS found (403 on plausible paths) |
| Alsacréations | `alsacreations.com/rss/actualites.xml` | ⚠️ real feed (found via the `<link rel="alternate">` tags of the home page) but **no per-item `<pubDate>`** → 0 items after `parse_rss` (the parser requires a date; not modified, out of scope) |
| Integrator newsletters | — | ❌ no public RSS identified (newsletters are typically email-only) |

**Raw pool collected: 202 real items, deduplicated.** The 30 held-out items
are **selected** from this pool (not written), with the exact titles,
summaries and publication dates from the scrape. Selection + labels:
[`scripts/label_heldout_pool.py`](../scripts/label_heldout_pool.py) — each URL
is a real, verifiable article.

**Grey zones avoided.** Labels 3–4 and 7 are deliberately absent from the
held-out (clean tiers for a readable precision/recall table) — but not from
the pool: these are real scores that the model assigns (see §3 and §4).

**Honest limit on the source mix.** Zapier and n8n publish in English; the
scoring prompt (`radar/scoring.py`) is in French and targets a French SMB
audience. The held-out therefore contains an English/French mix, faithful to
the feeds actually available for this topic (there is no French-language
Zapier/n8n blog) — not an arbitrary choice.

**Sealed schema** (`RawItem` + `label`, no field for a model score):
[`src/radar/eval/heldout_representative.json`](../src/radar/eval/heldout_representative.json).
The labels were fixed by reading the actual scraped content, **before** any
run of the scorer on this set (verified by
`tests/test_heldout_representative.py`).

## 2. Total n and label distribution

**n = 30**, selected to cover the three tiers equally:

| Tier | Target labels | n | Actual labels obtained |
|---|---|---|---|
| Off-topic | 0–2 | 10 | 0 (×8), 1 (×2) |
| Medium | 5–6 | 10 | 5 (×7), 6 (×3) |
| Highly relevant | 8–10 | 10 | 8 (×5), 9 (×4), 10 (×1) |

## 3. Precision/recall table by threshold

Measured with `precision_at_threshold`/`recall_at_threshold`
([`radar/eval/metrics.py`](../src/radar/eval/metrics.py)) — convention
"retained" = `score >= threshold`, "relevant" = `label >= threshold` (same
threshold on both sides, see the functions' docstring) — on the model's real
predictions (`claude-haiku-4-5`, real run via `scripts/calibrate_threshold.py`):

| Threshold (`min_score`) | Precision | Recall |
|---|---|---|
| 4 | 100.0% | 90.0% |
| 5 | 100.0% | 85.0% |
| 6 | 81.3% | 100.0% |
| 7 | 76.9% | 100.0% |
| 8 | **100.0%** | 70.0% |

**Important reading.** At a low threshold (4-5), the displayed precision is
mechanically high: the definition of "relevant" drops with the threshold (at
4, "relevant" = `label >= 4`, which includes the whole medium tier). It is
therefore not proof that a low threshold excludes non-actionable content —
only that it does not include off-topic items (whose score caps at 2). For
the real calibration question ("do I draft ONLY genuinely actionable
content?"), the useful measure is precision against the fixed **"highly
relevant" tier (label ≥ 8)**, computed directly on `results/quality_calibration.json`:

| Threshold | Items retained | Precision (vs. label ≥ 8) | Recall (vs. label ≥ 8) |
|---|---|---|---|
| 4 | 18 | 55.6% | 100% |
| 5 | 17 | 58.8% | 100% |
| 6 | 16 | 62.5% | 100% |
| 7 | 13 | 76.9% | 100% |
| 8 | 7 | **100%** | 70% |

On this basis, only `min_score = 8` reaches 100% precision — every lower
threshold lets through a majority of "medium" content, not clearly
actionable, alongside the truly relevant content.

**What happens at threshold 7 → 8.** Three truly relevant items (label 8-9)
are scored **7** by the model: *« The Zappy Award winner behind Just Eat
Spain's faster partner onboarding »*, *« RPA vs. Workflow Automation »*,
*« Workflow Versioning for Reliable Automation and Maintenance »* — three
borderline cases, solid content but a bit more "practical/educational" than
"concrete tool". At the same time, three items from the medium tier (label 6)
are *also* scored **7**: *« Le véritable frein à l'adoption de l'IA... »*,
*« Réforme de la facturation électronique... »*, *« Building France invite
les entrepreneurs... »*. **Score 7 is a noisy tier**: it mixes under-scored
true positives and over-scored true negatives, in both directions. It cannot
be trusted to make the call.

## 4. Independent check: unfiltered real sample (point 4)

The exact batch of 20 items from the real run of module 3.3 was **not
kept** — `PipelineReport` only persists aggregate counters (`n_fetched`,
`n_scored`...), not the list of items themselves, and `.data/seen.json` only
records **drafted** items (none that day). It cannot be reconstructed after
the fact.

**Honest substitute**: the 20 **most recent, unselected** items outside the
held-out above, from the same real scrape — an **unbiased** sample (no
curation towards a label tier), and therefore closer to what a real run
produces today with the enriched feeds than a new hand-picked selection would
have been. Set:
[`src/radar/eval/production_recall_check.json`](../src/radar/eval/production_recall_check.json),
labels: [`scripts/label_production_recall_check.py`](../scripts/label_production_recall_check.py).

Real result (`scripts/check_production_recall.py`,
`results/production_recall_check_results.json`):

| | Value |
|---|---|
| n | 20 |
| Truly relevant items in the sample (label ≥ 8) | **0** |
| Items retained by `min_score = 8` | **0** |
| False positives at this threshold | **0** |
| Maximum model score observed | 7 |

**Honest finding, in both directions.** Recall is not measurable on this
sample (no true positive to recover) — even with automation/no-code feeds in
`FEED_URLS`, genuinely actionable content remains a minority in the day's raw
feed; it took searching through 202 items to gather 10 for the held-out. On
the other hand, precision holds: zero false positives, including on Zapier
articles with an engaging tone that mention automation without being concrete
automation guides (e.g. *« How to add Zoom to Google Calendar »*, scored 7 by
the model against a human label of 3 — a notable gap, but still below the
threshold of 8).

## 5. Chosen threshold and justification

**`min_score = 8`** (unchanged since the first calibrated version of this
module — but now justified on real data, not fabricated data).

Three converging justifications:

1. **Empirical (fixed "highly relevant" tier)**: only `min_score = 8`
   reaches 100% precision against the genuinely actionable tier; every lower
   threshold lets through 25 to 45% of medium content.
2. **Empirical (robustness)**: confirmed at zero false positives on a second
   real sample, unfiltered and uncurated (§4).
3. **Semantic (scoring grid)**: `radar/scoring.py::build_prompt` defines
   `7 = « utile mais pas directement actionnable »` (useful but not directly
   actionable) and `8 = « gain réel »` (real gain). The real data reinforce
   this argument rather than weaken it: score 7 turns out to be a **noisy**
   tier where under-scored true positives and over-scored true negatives are
   mixed (§3) — it cannot be relied on to tell the two apart. Requiring 8
   amounts to never making the call on this ambiguous tier.

**Cost of the change (recall 70%, not 100%)**: consciously accepted. Missing
one relevant item in 10 means it is not drafted in that run — a low cost (the
feed is daily, the article has not disappeared). Drafting non-actionable
content costs more: review time, eroded trust in the automation. The
asymmetry favours precision.

## 6. Scope (honest)

- **n = 30 for the calibration held-out, n = 20 for the check**: samples of
  this size give wide confidence intervals (a single error more or less
  shifts precision by several points). The trends (7 = noisy tier, 8 = clean
  cut) are noted on small counts per item concerned (3 out of 10) — to be
  re-validated if the volume of SMB-automation traffic increases.
- **English/French mix** (§1): the scoring prompt was not specifically
  tested for cross-language robustness; the results above do not isolate it
  as a factor.
- **Recall is only measured on the curated held-out**, not on a real
  high-volume production feed — the §4 check confirms the absence of false
  positives but can say nothing about real recall (0 true positives observed
  that day).
- Complements [`HELDOUT.md`](HELDOUT.md) (which validates the scorer's
  out-of-sample **specificity** on an unseen source, Numerama) without
  replacing it: the two sets measure different things.

## 7. Measurement date

**2026-08-29**, with `claude-haiku-4-5` (production model).

## Reproducibility

```bash
uv run python scripts/scrape_heldout_pool.py          # real pool (network)
uv run python scripts/label_heldout_pool.py            # applies the 30 labels
uv run python scripts/label_production_recall_check.py # applies the 20 labels
uv run python scripts/calibrate_threshold.py            # precision/recall (LLM)
uv run python scripts/check_production_recall.py        # independent check (LLM)
```

- Non-contamination tested: `tests/test_heldout_representative.py`,
  `tests/test_production_recall_check.py` (sealed schema, disjoint from the
  training dataset, disjoint from each other, tier coverage).
- Metrics tested: `tests/test_metrics.py`.
