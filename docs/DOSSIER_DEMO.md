# Radar Automation — demo dossier

**A monitoring system that reads, sorts and drafts on its own, for two cents
a day — and in which every component was measured before being kept.**

*Khirami — Nassim · Data as of September 1, 2026 · Reading time: 10 minutes*

> **How to read this dossier.** Each section gives its **verdict** first, in
> one sentence, then the **numeric proof** that supports it, then a pointer to
> the **annex** for anyone who wants to verify. The nine sections can be read
> without any technical knowledge; the annexes are built to be audited.

---

## 1 — The verdict on one page

> **Verdict.** Three real runs over four days, no failures, four cents of
> total cost. The system works unattended and accounts for everything it does.

**Proof.**

| | Value | Source |
|---|---|---|
| Real runs recorded | **3** (Aug 29, Aug 30, Sep 1) | `docs/run_history.json` |
| Articles processed per run | 17 to 57 depending on the day | same |
| Cost of one run | **$0.0082 to $0.0214** | same |
| Cumulative cost of the three runs | **≈ $0.040** | same |
| Model calls | 73 | same |
| Failures | **0 out of 73** | same |
| Duration of a full run | **3.8 s** (traced run of Sep 1) | `run_trace.json` |
| Precision of the editorial filter | **100%**, zero false positives | `QUALITY.md` |
| Automated tests passing | **264** | repository test suite |
| Quantified architecture decisions | **7, including 1 rejection** | 7 documents |

*Annex A1 — `run_report.json`, `run_trace.json`, `docs/run_history.json`.*

---

## 2 — The problem, in human cost

> **Verdict.** The work this system replaces is reading and sorting work:
> long, daily, and with no added value until something has been found. The
> system does it in a few seconds, at a cost that does not show up on an
> invoice.

**Proof — the traced run of September 1, 17 articles.**

| | A human | The system |
|---|---|---|
| Fetch 17 articles from 7 feeds | ~2 min | 0.42 s |
| Read and judge the relevance of each | 17 × ~25 s ≈ **7 min** | 3.34 s |
| Decide | included | included |
| **Total** | **≈ 7 min 5 s** | **3.8 s** |
| Cost (€50/h fully loaded) | **€5.90** | **€0.0075** |

Time compression factor: **×112**.

> ⚠️ **Status of these figures.** The 25 seconds of sorting per article and the
> hourly cost of €50 are **declared hypotheses**, not measurements: the system
> can measure its own latency, it cannot measure yours. The output file
> carries this distinction explicitly (`value.baseline.measured = false`).
> Only the "The system" column is measured. Replace the hypotheses with your
> own figures: the equation is parametric and ships with the system.

**On a productive run** (August 30: 30 articles sorted, 3 drafts written),
the same equation gives ≈ **36 minutes** of human work, of which ≈ 2 minutes
of review remain your responsibility — i.e. ≈ **€28.50** of time avoided for
€0.02 of machine cost. A projection, not a measurement: the latency of that
particular run was not instrumented.

*Annex A4 — `OBSERVABILITY.md` §4, parameters and limits of the equation.*

---

## 3 — Three real runs, end to end

> **Verdict.** These are not scripted demonstrations: three dated executions,
> on public feeds, which you can replay yourself.

**Proof — the complete history, with no selection.**

| Date | Fetched | Fresh | Scored | Above threshold | Drafted | Calls | Failures | Cost |
|---|---|---|---|---|---|---|---|---|
| Aug 29 | 20 | 20 | 20 | 0 | 0 | 20 | 0 | $0.0106 |
| Aug 30 | 57 | 32 | 30 | **3** | **3** | 36 | 0 | $0.0214 |
| Sep 1 | 17 | 17 | 17 | 0 | 0 | 17 | 0 | $0.0082 |

**Two runs out of three produced nothing — and that is the intended behavior.**
The relevance threshold is calibrated never to draft on a mediocre article
(§5). A day without a truly actionable article is a day without a
publication, not a day of failure. A system that produced three posts every
day, no matter what, would be a system that forces its topics.

**The funnel of the productive run (August 30).**

```
57 fetched  →  57 deduplicated  →  32 recent (< 7 days)  →  32 never seen
   →  30 scored (budget cap)  →  3 above threshold  →  3 drafted
```

36 model calls: 30 scorings + 3 angle decisions + 3 drafts.
The count adds up to the exact call, and the system checks it itself.

**A real draft, as produced** (score 8/10):

> *Source: « Claude integrations: How to use Zapier with Claude », Zapier,
> Aug 26 — [zapier.com/blog/automate-claude](https://zapier.com/blog/automate-claude)*
>
> « Connecter Claude à vos outils métier via Zapier, c'est transformer vos
> workflows existants sans coder. Plutôt que de discuter avec Claude en mode
> conversationnel, l'automatisation via Zapier vous permet de chaîner des
> tâches complètes : enrichir vos contacts CRM, générer des emails
> personnalisés, traiter vos bases de données. Découvrez comment intégrer
> l'intelligence de Claude directement dans vos processus métier pour gagner
> du temps sur les tâches répétitives. »

To be judged on its **fidelity to the source**, not on its style: it is raw
material to validate in thirty seconds, not a published post (§7).

*Annex A2 — the three drafts of Aug 30 and their source articles.*

---

## 4 — Architecture: what I chose **not** to do

> **Verdict.** This system is not "a multi-agent architecture". It is
> deterministic wherever the sequence is known in advance, and only calls a
> model where judgment is genuinely required. That is what makes it
> predictable, auditable and inexpensive.

**Proof — the trade-off grid applied to each step.**

| | Who decides the next step | Cost / latency | Auditability |
|---|---|---|---|
| Deterministic flow | the code | minimal | the code *is* the trace |
| **Explicit orchestration** ← chosen | the code, but reified | minimal | **per-step trace, for free** |
| Agents (LLM loop) | the model, at every turn | high | low by default |

The sequence of this pipeline — fetch, deduplicate, filter, score, apply the
threshold, select, decide the angle, draft, mark — is **fixed regardless of
content**. Having a model decide "and now, which step?" would add cost,
latency and non-determinism for zero benefit.

**The only three steps entrusted to a model**, because they require real
judgment:

```
fetch → deduplicate → filter_fresh → filter_unseen → [ score ⟵ LLM ]
   → filter_by_min_score → select_top_k → [ angle ⟵ LLM ] → [ write ⟵ LLM ]
   → mark_seen
```

Ten steps, of which three call the model. Seven are pure code, tested,
instantaneous: on the traced run, they consume **0.43 seconds out of 3.78**.

*Annex A3 — `WORKFLOW.md`, full trade-off grid and typing decisions.*

---

## 5 — The guarantees

> **Verdict.** Six guarantees, each backed by a test that fails if it is
> violated. These are not intentions: they are delivery conditions.

**Proof.**

| Guarantee | Statement | Numeric proof |
|---|---|---|
| **Quality** | The system never drafts on an off-topic article | threshold calibrated at 8/10: **100% precision**, 0 false positives on two real datasets (n=30 and n=20) |
| **Budget** | Cost cannot run away | hard cap checked between each batch; overshoot bounded to 5 calls, never unbounded |
| **Robustness** | An API outage does not break the run | bounded retries with increasing wait on 429/529 only; a failing article is isolated, the run continues |
| **Idempotence** | The same article is never processed twice | marking as the last step, after success; verified over two consecutive runs |
| **Auditability** | Every run leaves a complete trace | timestamp, duration, cost and outcome **per step, per article and per call** |
| **Non-regression** | Nothing ships unless everything passes again | **264 automated tests**, run before every delivery |

**Latency, measured on the run of September 1:**

| | Value |
|---|---|
| Total run duration | **3.779 s** |
| Scoring step (17 articles) | 3.344 s |
| Cumulative time of the 17 calls | 13.383 s |
| **Parallelization gain** | **×4.0** |
| Slowest / median / fastest call | 1.061 s / 0.737 s / 0.667 s |
| Own cost of the orchestration engine | **0.0001 s** |

Thirteen seconds of calls compressed into three: parallelism is not a
promise, it is a measured ratio between two clocks.

*Annexes A3 and A4 — `CONCURRENCY.md`, `OBSERVABILITY.md`.*

---

## 6 — How decisions are made

> **Verdict.** Seven architecture decisions, each measured before being
> settled. One of them is a rejection — and it is the one I am most satisfied
> with.

**Proof.**

| Question asked | Actual measurement | Decision |
|---|---|---|
| Where should the relevance threshold be set? | precision/recall on 30 hand-annotated articles + a check on 20 others | **8/10** — 100% precision, 70% recall |
| Does the model over-score out of sample? | 15 articles from a never-seen source | agreement **0.93**, rank correlation **0.87** |
| Should the pipeline be structured into steps? | numerical equivalence proven, free traceability | **Kept** |
| Are two calls (angle then draft) better than one? | quality +0.27/6 on 10 items — **not significant** — but a forced angle avoided, cost ×1.67 | **Kept, on the asymmetry of the cost of error** |
| Can we parallelize without breaking the order? | equivalence under inverted latencies, budget, retries | **Kept** — ×4.0 gain measured |
| Does an automatic reviewer improve the drafts? | detection 100%, **but 67% false rejects** (n=14) | **Discarded** |
| Can auditability be proven and the gain quantified? | per-call trace, latencies, parallelization gain | **Kept**, with the measured/hypothesis boundary written into the code |

**The rejection, in detail.** I built a reviewer agent, wrote 17 tests,
measured it on 14 real drafts — and the numbers said no: two correct drafts
out of three would have been wrongly rejected. I also diagnosed the cause:
this reviewer had no more information than the drafter, so it could not judge
better. It remains in the repository, tested and documented, but
**disconnected**.

That is what you are buying. Not one more agent: a decision, and the ability
to say no to one's own work when the measurement contradicts it.

*Annex A4 — the seven decision documents, with their raw data.*

---

## 7 — Acknowledged limits

> **Verdict.** Here is what this system does not do. I would rather tell you
> now than let you discover it in production.

1. **70% recall, by choice.** Out of ten genuinely relevant articles, three
   are not drafted that day. A deliberate trade-off: missing an article costs
   little — the feed is daily, the article has not disappeared. Publishing a
   bad one costs your credibility. The asymmetry settles it in favor of
   precision.
2. **Two runs out of three produced nothing.** Truly actionable content is a
   minority in a raw RSS feed: it took going through 202 articles to gather
   10 worthy of a test set. The system is a demanding filter, not a content
   machine.
3. **Small samples.** n = 30, 20, 15, 14, 10 depending on the measurement.
   The trends are clear, the confidence intervals wide. To be revalidated at
   larger volume.
4. **Drafts, not publications.** The output is raw material to validate in
   thirty seconds. The final word remains human, by design — and that review
   time is deducted from the gain announced in §2, never ignored.
5. **The value equation quantifies time avoided, not benefit obtained.**
   It will never prove that the work being replaced had value.

---

## 8 — Autonomy and operations

> **Verdict.** The system runs on its own, archives itself, and alerts you
> when something out of the ordinary happens. Its operating cost is on the
> order of a quarter of a euro per month.

**Proof.**

| | Value |
|---|---|
| Average cost per run | **$0.0134** (3 real runs) |
| Projection at 21 runs / month | **≈ $0.28**, i.e. **≈ €0.26** |
| Archiving | each run timestamped, with counters, cost and drafts |
| Automatic alert | triggered on cost overrun or call failure |
| Human intervention over 4 days | **none** |

The history is comparable over time: three runs are already in it, and the
fourth will be added in the same format.

*Annex A5 — scheduling, reproduction commands.*

---

## 9 — And for your case

> **Verdict.** This dossier shows a monitoring radar. What transfers is not
> the radar: it is the method that decides what to build, and above all what
> not to build.

| Tier | What you get | Anchored in |
|---|---|---|
| **Architecture diagnostic** | The trade-off grid applied to your case: which steps stay deterministic, where an agent is justified, where it is not | §4 |
| **Build-ready architecture** | The costed plan, the specified guarantees, and the measurement protocol for each component **before** writing it | §5 and §6 |
| **Build and handover** | The system, its tests, its decision documents, its trace. You own everything, you can replay everything | §3 and annexes |

The same method applies to sorting inbound leads, qualifying support tickets,
or summarizing regulatory documents: same shape — a fixed sequence, two or
three points where judgment is needed.

**Next step.** Thirty minutes, by video call: I apply the grid from §4 to
your case and you leave with the trade-off analysis, whether or not you work
with me.

---

## Annexes

| # | Content | For whom |
|---|---|---|
| A1 | `run_report.json`, `run_trace.json`, `docs/run_history.json` — raw data of the three runs | Anyone who wants to verify the figures |
| A2 | The three drafts of Aug 30 and their source articles | Anyone who wants to judge the output |
| A3 | `WORKFLOW.md`, `CONCURRENCY.md`, `MIGRATION.md` — architecture and migration | Architect |
| A4 | `QUALITY.md`, `HELDOUT.md`, `ANGLE_AGENT.md`, `CRITIC_AGENT.md`, `OBSERVABILITY.md` — the measurements and the decisions | Anyone who wants to audit the method |
| A5 | Reproduction commands and scheduling | Anyone who wants to replay it |
| A6 | Stack and dependencies: Python, Pydantic, Claude Haiku 4.5 | Technical buyer |
