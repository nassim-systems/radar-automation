# CriticAgent — post-writing review (module 4.4)

## Decision

**Discarded.** The CriticAgent (`radar/drafting/critic.py`) stays in the
repository, tested (17 unit tests) and functional, but is **not wired** as a
`Step` in the radar workflow. No bounded rewrite loop to build — the "if
kept" clause does not apply.

## 1. Context

After the AngleAgent + WriterAgent decomposition (module 4.2), the natural
next step is an agent that reviews the already-written draft and rejects it
if it has a real defect: invented fact, forced angle, off editorial line, too
long. The explicit goal of this module was not to build it on principle, but
to **measure whether it brings real value** before wiring it.

## 2. The agent

[`radar/drafting/critic.py`](../src/radar/drafting/critic.py):
- `Verdict` (`accepted: bool`, `reasons: list[str]`).
- `check_length`: **pure check, no LLM** — length is a mechanical criterion,
  no judgment required (consistent with the arbitration grid of
  `WORKFLOW.md`: no LLM where a rule suffices).
- `build_critic_prompt` / `parse_verdict` / `critique_draft`: the LLM
  boundary only covers the three criteria that require real judgment
  (faithfulness, angle, tone). `critique_draft` short-circuits the LLM call
  if the mechanical defect is already sufficient — no needless cost.
- **Safe fail-closed default**: ambiguous or empty output → `REJETÉ`, never
  `ACCEPTÉ` wrongly (same error-cost asymmetry as `QUALITY.md`/
  `ANGLE_AGENT.md`).

17 unit tests (`tests/test_critic_agent.py`): sentence-counting heuristic,
robust parsing (missing prefix, multiple reasons, empty/ambiguous output),
short-circuit verified by a fake `LLMClient` that raises an `AssertionError`
if it is called.

## 3. Measurement method

[`radar/eval/critic_test_set.py`](../src/radar/eval/critic_test_set.py): 14
drafts — **6 good ones, reused as-is** from the real run of module 4.2
(`results/draft_strategy_comparison.json`, already judged good in `ANGLE_AGENT.md`)
and **8 deliberately defective**, two per requested category, built by hand
for this test (the source articles remain real).
[`scripts/measure_critic_agent.py`](../scripts/measure_critic_agent.py) runs
`critique_draft` with real LLM calls on the 14 cases and computes the
detection rate / false-reject rate.

**Bug encountered and fixed before any conclusion**: the first run used
`AnthropicClient()` without specifying `max_tokens`, falling back to the
default of 16 (sized for scoring — an integer). The reasons were truncated
mid-word (« Fait inventé - », « Ton non profession »). Fixed
(`max_tokens=256`, the same error already encountered for drafting in 3.3)
and **re-measured before writing anything below** — the numbers did not move
(the truncation affected the displayed reasons, not the verdict itself), but
the diagnosis of the real cause, below, was only readable after the fix.

## 4. Quantified results

| | Value |
|---|---|
| n | 14 (8 defective, 6 good) |
| **Detection** | **8/8 (100%)** |
| **False rejects** | **4/6 (67%)** |
| Run cost | 0.0103 USD |

Detail: [`results/critic_agent_measurement.json`](../results/critic_agent_measurement.json).

**Perfect detection by category**: fabricated fact 2/2, forced angle 2/2,
off editorial line 2/2, too long 2/2 (the last two with no false positive
observed on the good drafts).

**The 4 false rejects, in detail** (Rozas, Goose, Base44, Just Eat Spain) —
all cite « Angle forcé » (forced angle), and one also « Fait inventé »
(fabricated fact):
- *Goose* rejected because the draft says « vous gardez le contrôle de vos
  données, fini la dépendance aux API cloud » (you keep control of your data,
  no more dependence on cloud APIs) while the summary given to the critic
  only says « un agent IA local » (a local AI agent) — the critic treats a
  reasonable inference (local execution ⇒ no cloud dependence) as a
  fabrication.
- *Rozas* rejected because « chaque demande traitée en 2 minutes » (every
  request handled in 2 minutes) rephrases « give every lead a 2-minute
  headstart » — a debatable but defensible paraphrase, not an invention.
- *Base44*, *Just Eat Spain*: same pattern — the critic requires the SMB link
  to be **literally stated** in the source summary, otherwise it labels it
  « artificiel » (artificial).

## 5. Analysis: why it does not work here

**This is not an artefact of the test protocol — it is structural.** The
critic only receives `item.summary`, exactly the same short RSS summary (1-2
sentences) that the writer already used to write the draft: it is the
**only** material this project passes around (no step retrieves the full
article — see `radar/domain.py::RawItem`). The critic therefore structurally
has no more information than the writer to tell a "reasonable rephrasing"
from an "invented fact", nor to judge whether the SMB link is honest — which
is exactly the work the AngleAgent (module 4.2) has already done, with the
same level of information. Having a second agent re-judge the angle on the
same data can only duplicate a judgment already made or contradict it at
random — which is what we observe.

**The critic's "forced angle" criterion is the main culprit**: it appears in
all 4 false rejects. The mechanical (length) and tone (spam, English)
criteria produced **no** false positives in this measurement.

## 6. Reasoned decision

**Discarded**, on the real figures above: a false-reject rate of 67% would
mean, in production, that only one truly good draft in three would survive
the critic. The radar already produces few drafts (`min_score=8`, calibrated
in 3.5, to stay demanding upstream) — an additional filter that removes
two-thirds more of them would cancel most of the pipeline's value. The 100%
detection does not compensate: it covers gross defects (invented figures,
spam, length) that a narrower check would already catch without the massive
false rejection — the flaw is not detection, it is the scope of the judgment
requested (faithfulness + angle) applied with the same limited information
as the writer.

**Option deliberately not pursued here**: a critic restricted to length
(already pure, zero false positives) and tone/language (zero false positives
measured), without re-judging the angle or fine factual faithfulness, would
probably be defensible — but it is a different agent from the one specified,
and measuring it properly would require a new dedicated measurement. I did
not do it here so as not to keep tweaking the prompt until an acceptable
number came out: the measurement is that of the critic as specified, and the
verdict matches it.

## Reproducibility

```bash
uv run python scripts/measure_critic_agent.py
```

Writes `results/critic_agent_measurement.json` (verdict + reasons per item,
detection/false-reject rates, real cost).
