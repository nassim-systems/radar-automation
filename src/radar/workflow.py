"""The radar pipeline expressed as a ``Workflow`` (module 4.1), with the
decomposed AngleAgent + WriterAgent variant (module 4.2, kept after
measurement: see ``ANGLE_AGENT.md``) and a bounded concurrent ``ScoreStep``
(module 4.3: see ``CONCURRENCY.md``).

Since module 4.5 (``MIGRATION.md``), ``build_radar_steps_production`` is
the **only** production path, wired in ``composition.py``.
``run_pipeline`` (module 1.x, the sequential monolithic function) was
removed: dead path eliminated, it is no longer "a parallel demonstration",
it is production. ``build_radar_steps``/
``build_radar_steps_decomposed`` (mono/decomposed, sequential scoring)
remain as tested alternative compositions, useful for the recomposition
proof (see ``WORKFLOW.md``); not wired in production.

No step reimplements logic: each ``Step`` delegates to a pure function:
``deduplicate``, ``filter_fresh``, ``filter_unseen``,
``score_item``/``score_items_concurrently``, ``filter_by_min_score``,
``select_top_k``, ``build_draft_prompt``/``parse_draft`` (single-call),
``decide_angle``/``write_draft`` (decomposed).
"""
from collections.abc import Callable

from pydantic import Field

from core.usage import ListUsageSink
from core.workflow.engine import Step
from core.workflow.models import WorkflowState
from radar.concurrent_scoring import ConcurrentScoringConfig, score_items_concurrently
from radar.decision.models import ScoredItem
from radar.decision.select_top_k import select_top_k
from radar.domain import RawItem
from radar.drafting.angle import Angle, decide_angle
from radar.drafting.parse import parse_draft
from radar.drafting.prompt import build_draft_prompt
from radar.drafting.writer import write_draft
from radar.ingest import deduplicate, filter_fresh, filter_unseen, item_key
from radar.llm.base import LLMClient
from radar.llm.timing import CallSubject, CallTimeline, TimedLLMClient
from radar.pipeline import (
    PipelineConfig,
    PipelineReport,
    ScoredDraft,
    filter_by_min_score,
)
from radar.scoring import score_item
from radar.tools.seen_store import SeenStore


class RadarWorkflowState(WorkflowState):
    """Concrete state of the radar workflow: one field per pipeline stage.

    Typed fields (not a generic bag): see the "WorkflowState typing"
    decision in ``WORKFLOW.md``.
    """

    fetched: list[RawItem] = Field(default_factory=list)
    deduped: list[RawItem] = Field(default_factory=list)
    fresh: list[RawItem] = Field(default_factory=list)
    unseen: list[RawItem] = Field(default_factory=list)
    scored: list[ScoredItem] = Field(default_factory=list)
    above_threshold: list[ScoredItem] = Field(default_factory=list)
    top_k: list[ScoredItem] = Field(default_factory=list)
    angled: list[tuple[ScoredItem, Angle]] = Field(default_factory=list)
    drafts: list[ScoredDraft] = Field(default_factory=list)
    n_failures: int = 0
    n_skipped_no_angle: int = 0
    n_llm_calls: int = 0


def _as_radar_state(state: WorkflowState) -> RadarWorkflowState:
    """Narrow ``WorkflowState`` to the concrete radar workflow state.

    Without static checking (this project does not run mypy), this step turns a
    composition error into an explicit, immediate ``TypeError`` rather than a
    confusing ``AttributeError`` later in the step.
    """
    if not isinstance(state, RadarWorkflowState):
        raise TypeError(
            f"attendu RadarWorkflowState, reçu {type(state).__name__}"
        )
    return state


def _timed(
    llm: LLMClient,
    timeline: CallTimeline | None,
    phase: str,
    item: RawItem,
) -> LLMClient:
    """Decorate ``llm`` to attribute its calls to ``item`` within ``phase``.

    Without a timeline, return the client unchanged: instrumentation is strictly
    optional and introduces no different code path in the steps
    (module 4.6, see ``OBSERVABILITY.md``). The phase name is the step's name,
    which is what later lets us match the cumulated call time against the
    step's wall time.
    """
    if timeline is None:
        return llm
    return TimedLLMClient(
        llm,
        timeline,
        phase=phase,
        subject=CallSubject(key=item_key(item), title=item.title, url=item.url),
    )


class FetchStep:
    name = "fetch"

    def __init__(self, fetch_items: Callable[[], list[RawItem]]) -> None:
        self._fetch_items = fetch_items

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        return s.model_copy(update={"fetched": self._fetch_items()})


class DeduplicateStep:
    name = "deduplicate"

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        return s.model_copy(update={"deduped": deduplicate(s.fetched)})


class FilterFreshStep:
    name = "filter_fresh"

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        fresh = filter_fresh(
            s.deduped, now=self._config.now, max_age=self._config.max_age
        )
        return s.model_copy(update={"fresh": fresh})


class FilterUnseenStep:
    name = "filter_unseen"

    def __init__(self, seen_store: SeenStore) -> None:
        self._seen_store = seen_store

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        unseen = filter_unseen(s.fresh, self._seen_store.load_seen())
        return s.model_copy(update={"unseen": unseen})


class ScoreStep:
    name = "score"

    def __init__(
        self,
        llm: LLMClient,
        config: PipelineConfig,
        timeline: CallTimeline | None = None,
    ) -> None:
        self._llm = llm
        self._config = config
        self._timeline = timeline

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        candidates = s.unseen[: self._config.max_scored]
        scored = [
            ScoredItem(
                item=item,
                score=score_item(
                    item, _timed(self._llm, self._timeline, self.name, item)
                ).score,
            )
            for item in candidates
        ]
        return s.model_copy(
            update={
                "scored": scored,
                "n_llm_calls": s.n_llm_calls + len(candidates),
            }
        )


class ConcurrentScoreStep:
    """Concurrent variant of ``ScoreStep`` (module 4.3): same output field
    (``state.scored``, in item input order), bounded by
    ``ConcurrentScoringConfig`` (concurrency, hard budget, retry/backoff)
    rather than by a sequential loop. Drop-in: replaces ``ScoreStep``
    in any ``Step`` list without touching the other steps.
    See ``CONCURRENCY.md`` for the decisions (defaults, budget policy,
    retry)."""

    name = "score"

    def __init__(
        self,
        llm: LLMClient,
        pipeline_config: PipelineConfig,
        concurrency_config: ConcurrentScoringConfig | None = None,
        usage_sink: ListUsageSink | None = None,
        timeline: CallTimeline | None = None,
    ) -> None:
        self._llm = llm
        self._pipeline_config = pipeline_config
        self._concurrency_config = concurrency_config
        self._usage_sink = usage_sink
        self._timeline = timeline

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        candidates = s.unseen[: self._pipeline_config.max_scored]
        report = score_items_concurrently(
            candidates,
            self._llm,
            config=self._concurrency_config,
            usage_sink=self._usage_sink,
            wrap_llm=(
                None
                if self._timeline is None
                else lambda item: _timed(self._llm, self._timeline, self.name, item)
            ),
        )
        return s.model_copy(
            update={
                "scored": report.scored,
                "n_failures": s.n_failures + report.n_failures,
                "n_llm_calls": s.n_llm_calls + report.n_attempted + report.n_retries,
            }
        )


class FilterByMinScoreStep:
    name = "filter_by_min_score"

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        above = filter_by_min_score(s.scored, self._config.min_score)
        return s.model_copy(update={"above_threshold": above})


class SelectTopKStep:
    name = "select_top_k"

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        top = select_top_k(s.above_threshold, self._config.k)
        return s.model_copy(update={"top_k": top})


class DraftStep:
    """Isolate LLM failures item by item, same policy as
    ``run_pipeline``: only the ``llm.complete`` call is isolated; a code bug
    (prompt/parsing) propagates. Fine-grained resilience stays here, in the
    step; ``run_workflow`` only handles failure of the whole step
    (see ``WORKFLOW.md``)."""

    name = "draft"

    def __init__(self, llm: LLMClient, timeline: CallTimeline | None = None) -> None:
        self._llm = llm
        self._timeline = timeline

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        drafts: list[ScoredDraft] = []
        n_failures = 0
        for entry in s.top_k:
            prompt = build_draft_prompt(entry.item)
            llm = _timed(self._llm, self._timeline, self.name, entry.item)
            try:
                response = llm.complete(prompt)
            except Exception:
                n_failures += 1
                continue
            draft = parse_draft(response)
            drafts.append(ScoredDraft(item=entry.item, score=entry.score, draft=draft))
        return s.model_copy(
            update={
                "drafts": drafts,
                "n_failures": s.n_failures + n_failures,
                "n_llm_calls": s.n_llm_calls + len(s.top_k),
            }
        )


class AngleStep:
    """Decide the editorial angle of each top-k item (module 4.2).

    ``Angle.has_angle=False`` is a legitimate outcome, not a failure: it is
    precisely what the single-call ``DraftStep`` lacked; it always writes
    something even when no honest SME angle exists. See ``ANGLE_AGENT.md``
    for the measurement that motivated this choice.

    **Per-item isolation** (production hardening, module 4.5): an LLM failure
    on one item's angle decision does not take down the others. The item is
    counted in ``n_failures`` and stays "unseen" (no draft, retried on the
    next run), same policy as ``ScoreStep``/``WriteStep``. Before this
    hardening, a single failed call would have failed the whole step (hence
    the whole run, see ``core.workflow.engine.WorkflowError``): acceptable
    for a one-off measurement (4.2), not for the only production path.
    """

    name = "angle"

    def __init__(self, llm: LLMClient, timeline: CallTimeline | None = None) -> None:
        self._llm = llm
        self._timeline = timeline

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        angled: list[tuple[ScoredItem, Angle]] = []
        n_failures = 0
        for entry in s.top_k:
            llm = _timed(self._llm, self._timeline, self.name, entry.item)
            try:
                angle = decide_angle(entry.item, llm)
            except Exception:
                n_failures += 1
                continue
            angled.append((entry, angle))
        return s.model_copy(
            update={
                "angled": angled,
                "n_failures": s.n_failures + n_failures,
                "n_llm_calls": s.n_llm_calls + len(s.top_k),
            }
        )


class WriteStep:
    """Write only the items with an angle kept by ``AngleStep``;
    replaces ``DraftStep`` in the decomposed composition. Same per-item
    LLM failure isolation as ``DraftStep``."""

    name = "write"

    def __init__(self, llm: LLMClient, timeline: CallTimeline | None = None) -> None:
        self._llm = llm
        self._timeline = timeline

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        drafts: list[ScoredDraft] = []
        n_failures = 0
        n_skipped = 0
        n_attempted = 0
        for entry, angle in s.angled:
            if not angle.has_angle:
                n_skipped += 1
                continue
            n_attempted += 1
            llm = _timed(self._llm, self._timeline, self.name, entry.item)
            try:
                draft = write_draft(entry.item, angle, llm)
            except Exception:
                n_failures += 1
                continue
            drafts.append(ScoredDraft(item=entry.item, score=entry.score, draft=draft))
        return s.model_copy(
            update={
                "drafts": drafts,
                "n_failures": s.n_failures + n_failures,
                "n_skipped_no_angle": n_skipped,
                "n_llm_calls": s.n_llm_calls + n_attempted,
            }
        )


class MarkSeenStep:
    """Idempotence: mark as seen only the items drafted successfully, like
    ``run_pipeline``. A step in its own right (not a hidden side effect in
    ``DraftStep``): a dry-run scoring workflow can simply omit this
    step without duplicating code."""

    name = "mark_seen"

    def __init__(self, seen_store: SeenStore) -> None:
        self._seen_store = seen_store

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        self._seen_store.add_seen(item_key(sd.item) for sd in s.drafts)
        return s


def build_radar_steps(
    *,
    fetch_items: Callable[[], list[RawItem]],
    seen_store: SeenStore,
    llm: LLMClient,
    config: PipelineConfig,
    timeline: CallTimeline | None = None,
) -> list[Step]:
    """Wire the radar's 9 steps in the order of ``run_pipeline``.

    Pure composition: no step is instantiated differently from what the
    ``run_pipeline`` function (removed in module 4.5) already wired, with the
    same ``PipelineConfig`` and no duplicated fields. Tested alternative
    composition (sequential scoring, single-call); production uses
    ``build_radar_steps_production``. A caller who wants a different workflow
    (e.g. a dry-run without drafting) recomposes its own list from the same
    classes rather than duplicating this function.
    """
    return [
        FetchStep(fetch_items),
        DeduplicateStep(),
        FilterFreshStep(config),
        FilterUnseenStep(seen_store),
        ScoreStep(llm, config, timeline),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        DraftStep(llm, timeline),
        MarkSeenStep(seen_store),
    ]


def build_radar_steps_decomposed(
    *,
    fetch_items: Callable[[], list[RawItem]],
    seen_store: SeenStore,
    llm: LLMClient,
    config: PipelineConfig,
    timeline: CallTimeline | None = None,
) -> list[Step]:
    """Decomposed variant (module 4.2): ``AngleStep`` + ``WriteStep``
    replace ``DraftStep``. Kept after a measured comparison on the real
    held-out set; see ``ANGLE_AGENT.md`` (decision, cost, examples).
    """
    return [
        FetchStep(fetch_items),
        DeduplicateStep(),
        FilterFreshStep(config),
        FilterUnseenStep(seen_store),
        ScoreStep(llm, config, timeline),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        AngleStep(llm, timeline),
        WriteStep(llm, timeline),
        MarkSeenStep(seen_store),
    ]


def build_radar_steps_production(  # noqa: PLR0913
    *,
    fetch_items: Callable[[], list[RawItem]],
    seen_store: SeenStore,
    llm: LLMClient,
    config: PipelineConfig,
    concurrency_config: ConcurrentScoringConfig | None = None,
    usage_sink: ListUsageSink | None = None,
    timeline: CallTimeline | None = None,
) -> list[Step]:
    """Production composition (module 4.5, see ``MIGRATION.md``):
    bounded concurrent scoring (module 4.3) + decomposed AngleAgent/
    WriterAgent drafting (module 4.2, the only decomposition measured and kept).
    This is the only composition wired in ``composition.py``.

    7 parameters, 7 genuinely distinct injection seams (no natural grouping
    like ``PipelineConfig`` for the other composers). ``noqa`` is deliberate
    rather than an artificial config object.

    ``timeline`` (module 4.6) is optional: without it, the composition is
    identical to what it was, and no step takes a different code path.
    See ``OBSERVABILITY.md``.

    ``usage_sink`` must be the **same** sink as the one injected into the
    caller's ``AnthropicClient``: ``ConcurrentScoreStep`` uses it to check
    ``max_cost_usd`` between two batches (see ``CONCURRENCY.md``).
    Passing a different sink (or none) silently disables the hard budget;
    scoring still works, just without a cost cap.
    """
    return [
        FetchStep(fetch_items),
        DeduplicateStep(),
        FilterFreshStep(config),
        FilterUnseenStep(seen_store),
        ConcurrentScoreStep(llm, config, concurrency_config, usage_sink, timeline),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        AngleStep(llm, timeline),
        WriteStep(llm, timeline),
        MarkSeenStep(seen_store),
    ]


def radar_workflow_state_to_pipeline_report(state: WorkflowState) -> PipelineReport:
    """Project the final workflow state onto the existing ``PipelineReport``
    contract (``run_report.json``, ``RunRecord``, unchanged since module
    3.3, no regression on its schema). ``n_skipped_no_angle`` (module
    4.2) has no equivalent in ``PipelineReport``: this information
    stays visible on the full state / the ``WorkflowRun``, not duplicated here.
    """
    s = _as_radar_state(state)
    return PipelineReport(
        n_fetched=len(s.fetched),
        n_dedup=len(s.deduped),
        n_fresh=len(s.fresh),
        n_unseen=len(s.unseen),
        n_scored=len(s.scored),
        n_above_threshold=len(s.above_threshold),
        n_drafted=len(s.drafts),
        n_llm_calls=s.n_llm_calls,
        n_failures=s.n_failures,
        drafts=s.drafts,
    )
