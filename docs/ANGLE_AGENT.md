# AngleAgent + WriterAgent — decomposition of drafting (module 4.2)

## Decision

**Kept.** Wired as `AngleStep` + `WriteStep` in
[`radar/workflow.py`](../src/radar/workflow.py)
(`build_radar_steps_decomposed`). Not wired into `composition.py` /
`run_pipeline` (production) at the time of this module — see "Scope" at the
end of the document. **Update (module 4.5)**: `AngleStep`/`WriteStep` are
now in production, via `build_radar_steps_production` — see
`MIGRATION.md`.

## 1. Context

The current single-call approach (`build_draft_prompt`) does two things in a
single LLM call: decide whether an SMB angle exists and write the post. The
real run of module 3.3 had revealed a symptom: an article about home
batteries for data centers, scored 1/10 for relevance, had been given a
post forcing an artificial SMB link (« *Cette initiative pourrait offrir
aux PME une nouvelle opportunité...* » — "This initiative could offer SMBs
a new opportunity..."). The single call has no way to answer "there is
nothing honest to draw from this" — it must always produce text.

## 2. The two agents

- [`radar/drafting/angle.py`](../src/radar/drafting/angle.py): `Angle`
  (`has_angle: bool`, `angle: str | None`), `build_angle_prompt`,
  `parse_angle`, `decide_angle`. Writes nothing — only judges whether an
  honest angle exists.
- [`radar/drafting/writer.py`](../src/radar/drafting/writer.py):
  `build_writer_prompt`, `write_draft`. No longer decides the angle — writes
  from the one supplied by the `Angle`. Reuses the existing `parse_draft`
  (no duplicated parsing).

Each agent has its own LLM boundary, tested in isolation with `FakeLLM`
(`tests/test_angle_agent.py`, `tests/test_writer_agent.py` — 16 tests:
robust parsing on prefix/missing marker, empty response, multiline output,
different verdicts scripted per item).

## 3. Measurement method

[`scripts/compare_draft_strategies.py`](../scripts/compare_draft_strategies.py)
runs both strategies, with real LLM calls, on the **10 "highly relevant"
items (label ≥ 8)** of the sealed held-out set from module 3.5
(`heldout_representative.json`) — the real population that reaches the
drafting stage in production (`min_score = 8`). Raw result:
[`results/draft_strategy_comparison.json`](../results/draft_strategy_comparison.json).

**Quality metric**: human judgment on each draft (0–2 per criterion, myself
as annotator — same non-independence limit as everywhere else in this
project, see `QUALITY.md`):
- **Faithfulness**: no invented facts, consistent with the article.
- **Naturalness of the angle**: is the SMB link honest or does it feel
  forced?
- **Actionability**: does the reader leave with something concrete?

## 4. Quantified results

**Actual cost** (`ListUsageSink`, module 3.4):

| | Tokens in/out | Cost USD |
|---|---|---|
| Single call (10 calls) | 2,235 / 1,340 | 0.0089 |
| Decomposed (10 angle + 9 write) | 5,927 / 1,796 | 0.0149 |

**×1.67, not ×2**: skipping an item with no honest angle saves a writing
call — the overhead is not a mechanical doubling, it depends on the share of
items with no honest angle.

**Quality (0–6, second, stricter review — my first pass was too generous
and gave an almost uniform score)**:

| # | Item | Single | Decomposed | Delta |
|---|---|---|---|---|
| 1 | Best automation software for SMB | 5 | 6 | +1 |
| 2 | Rozas (Zapier) | 5 | 5 | 0 |
| 3 | Zapier MCP | 4 | 6 | +2 |
| 4 | Just Eat Spain onboarding | 6 | 5 | **−1** |
| 5 | Amazon Bedrock AgentCore | 4 | *(no draft)* | angle judged absent |
| 6 | RPA vs Workflow Automation | 5 | 6 | +1 |
| 7 | Workflow Versioning | 6 | 6 | 0 |
| 8 | Goose | 6 | 6 | 0 |
| 9 | Base44 | 6 | 6 | 0 |
| 10 | Scraper Studio | 6 | 5 | **−1** |
| | **Average** | **5.4** (n=10) | **5.67** (n=9, item 5 not scored) | +0.27 |

**Honest reading**: on the average alone, the improvement is **small and
non-uniform** — two items (4, 10) are even slightly *less* actionable on the
decomposed side (the more elaborate angle sometimes pulls toward a more
abstract conclusion than the direct "for an SMB, this means..." translation
of the single call). On 6 of the 10 items, the quality gap is zero or
marginal. A comparison looking *only* at the average would not clearly
justify the ×1.67 overhead.

**What justifies the decision is not the average — it is item 5.**
On a real article from this same run (multi-agent with client memory on AWS
Bedrock), the AngleAgent judged that no honest SMB angle existed, and
**skipped** — reproducing exactly, on a fresh example independent of the
historical symptom from 3.3, the failure this module was meant to fix. The
single call, for its part, wrote anyway, with a conclusion that felt
tacked on (« *une expérience client plus fluide et efficace, même pour les
PME* » — "a smoother and more efficient customer experience, even for
SMBs" — scored 4/6, losing a point on the naturalness of the angle).

## 5. Reasoned decision

**Kept**, for three reasons, in order of importance:

1. **Asymmetry of the cost of error, not the average.** As already
   established in `QUALITY.md` (calibration of `min_score`): a missed draft
   costs little (nothing is published, we retry), a forced draft that gets
   published costs more (eroded credibility). Item 5 is the proof, on this
   run, that the decomposition eliminates this specific risk — even if the
   average quality only improves marginally elsewhere.
2. **Negligible absolute cost at the project's real scale.** ×1.67 on a run
   that drafts 0 to a few items (the real runs of 3.3/3.4/3.5 all drafted 0
   items) amounts to a few thousandths of a dollar per run. The relative
   ratio (×1.67) is correct but misleading if extrapolated without looking
   at the real volume.
3. **Free observability.** The angle becomes an explicit, inspectable
   artifact (`Angle.has_angle`/`Angle.angle`) instead of an implicit
   decision buried in a single call — consistent with the spirit of module
   4.1 (per-step traceability).

**Cheaper alternative considered, not retained for this measurement**:
adding to the single-call prompt an explicit option "if no honest SMB link,
answer AUCUN BROUILLON" ("NO DRAFT") might capture most of the benefit of
item 5 at no extra cost. I did not test it — it is a legitimate follow-up
lead, not an argument against the decomposition as measured here.

**What this measurement does not prove**: at n=10, the average gap (+0.27)
has no statistical robustness. If the goal had been "the decomposition makes
every draft better", the measured answer would rather be no. The goal
actually achieved is narrower: "the decomposition prevents the worst possible
error (a forced angle) without ever producing a clearly worse result across
the set".

## 6. Integration

`AngleStep` and `WriteStep` (`radar/workflow.py`) replace `DraftStep` in
`build_radar_steps_decomposed` — same item-by-item isolation of LLM
failures, same `mark_seen` policy (an item with no honest angle stays
unseen, retried on the next run, exactly like a draft failure).
Tested: `tests/test_radar_workflow_decomposed.py` (step order, effective
skip, non-marking of skipped items, usage capture across
score+angle+write).

**Scope (at the time of this module)**: not wired into
`composition.py::build_radar_pipeline` (production, still `run_pipeline`
+ single call). Consistent with the scope already set in `WORKFLOW.md`: this
module adds a measured and tested capability, it does not migrate the
production path unless asked.

**Update (module 4.5, `MIGRATION.md`)**: the production path has since been
consolidated onto this workflow — `AngleStep`/`WriteStep` are now wired
into `composition.py` via `build_radar_steps_production`, and `run_pipeline`
has been removed.

## Reproducibility

```bash
uv run python scripts/compare_draft_strategies.py
```

Writes `results/draft_strategy_comparison.json` (drafts of both strategies + actual
cost). The quality judgment (§4 table) is a manual review of this file, not
an automated computation.
