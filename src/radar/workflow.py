"""Le pipeline radar exprimé comme un ``Workflow`` (module 4.1) — avec la
variante décomposée AngleAgent + WriterAgent (module 4.2, retenue après
mesure : voir ``ANGLE_AGENT.md``) et un ``ScoreStep`` concurrent borné
(module 4.3 : voir ``CONCURRENCY.md``).

Depuis le module 4.5 (``MIGRATION.md``), ``build_radar_steps_production``
est l'**unique** chemin de production, câblé dans ``composition.py``.
``run_pipeline`` (module 1.x, la fonction monolithique séquentielle) a été
supprimée — voie morte éliminée, ce n'est plus « une démonstration
parallèle », c'est la production. ``build_radar_steps``/
``build_radar_steps_decomposed`` (mono/décomposé, scoring séquentiel)
restent comme compositions alternatives testées, utiles pour la preuve de
recomposition (cf. ``WORKFLOW.md``) — pas câblées en production.

Aucune étape ne réimplémente de logique : chaque ``Step`` délègue à une
fonction pure — ``deduplicate``, ``filter_fresh``, ``filter_unseen``,
``score_item``/``score_items_concurrently``, ``filter_by_min_score``,
``select_top_k``, ``build_draft_prompt``/``parse_draft`` (mono-appel),
``decide_angle``/``write_draft`` (décomposé).
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
    """État concret du workflow radar — un champ par étage du pipeline.

    Champs typés (pas un sac générique) : cf. la décision « typage de
    WorkflowState » dans ``WORKFLOW.md``.
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
    """Rétrécit ``WorkflowState`` vers l'état concret du workflow radar.

    Sans vérification statique (ce projet n'exécute pas mypy), cette étape
    transforme une erreur de composition en ``TypeError`` explicite et
    immédiate plutôt qu'un ``AttributeError`` confus plus loin dans l'étape.
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
    """Décore ``llm`` pour attribuer ses appels à ``item`` dans ``phase``.

    Sans timeline, renvoie le client tel quel : l'instrumentation est
    strictement optionnelle et n'introduit aucun chemin de code différent
    dans les étapes (module 4.6, cf. ``OBSERVABILITY.md``). Le nom de phase
    est celui de l'étape — c'est ce qui permet de rapprocher plus tard le
    temps cumulé des appels du temps réel de l'étape.
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
    """Variante concurrente de ``ScoreStep`` (module 4.3) — même champ de
    sortie (``state.scored``, dans l'ordre d'entrée des items), bornée par
    ``ConcurrentScoringConfig`` (concurrence, budget dur, retry/backoff)
    plutôt que par une boucle séquentielle. Drop-in : remplace ``ScoreStep``
    dans n'importe quelle liste de ``Step`` sans toucher aux autres étapes.
    Voir ``CONCURRENCY.md`` pour les décisions (défauts, politique de
    budget, retry)."""

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
    """Isolation des échecs LLM item par item — même politique que
    ``run_pipeline`` : seul l'appel ``llm.complete`` est isolé, un bug de
    code (prompt/parsing) se propage. La résilience fine reste ici, dans
    l'étape ; ``run_workflow`` ne gère que l'échec au niveau de l'étape
    entière (cf. ``WORKFLOW.md``)."""

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
    """Décide l'angle éditorial de chaque item du top-k (module 4.2).

    ``Angle.has_angle=False`` est une issue légitime, pas un échec : c'est
    précisément ce qui manquait au mono-appel ``DraftStep``, qui rédige
    toujours quelque chose même quand aucun angle PME honnête n'existe. Voir
    ``ANGLE_AGENT.md`` pour la mesure ayant motivé ce choix.

    **Isolation par item** (durcissement production, module 4.5) : un échec
    LLM sur la décision d'angle d'un item n'abat pas les autres — l'item est
    compté dans ``n_failures`` et reste « à voir » (pas de draft, retenté au
    run suivant), même politique que ``ScoreStep``/``WriteStep``. Avant ce
    durcissement, un seul appel raté aurait fait échouer toute l'étape (donc
    tout le run, cf. ``core.workflow.engine.WorkflowError``) — acceptable
    pour une mesure ponctuelle (4.2), pas pour le seul chemin de production.
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
    """Rédige uniquement les items avec un angle retenu par ``AngleStep`` —
    remplace ``DraftStep`` dans la composition décomposée. Même isolation
    des échecs LLM item par item que ``DraftStep``."""

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
    """Idempotence : ne marque vus que les items draftés avec succès — comme
    ``run_pipeline``. Étape à part entière (pas un effet de bord caché dans
    ``DraftStep``) : un workflow de scoring à blanc peut simplement omettre
    cette étape sans dupliquer de code."""

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
    """Câble les 9 étapes du radar dans l'ordre de ``run_pipeline``.

    Pure composition — aucune des étapes n'est instanciée différemment de ce
    que la fonction ``run_pipeline`` (supprimée au module 4.5) câblait déjà —
    même ``PipelineConfig``, pas de champs dupliqués. Composition
    alternative testée (scoring séquentiel, mono-appel) ; la production
    utilise ``build_radar_steps_production``. Un appelant qui veut un
    workflow différent (ex. un dry-run sans drafting) recompose sa propre
    liste à partir des mêmes classes plutôt que de dupliquer cette fonction.
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
    """Variante décomposée (module 4.2) : ``AngleStep`` + ``WriteStep``
    remplacent ``DraftStep``. Retenue après comparaison mesurée sur le
    held-out réel — voir ``ANGLE_AGENT.md`` (décision, coût, exemples).
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
    """Composition de production (module 4.5, voir ``MIGRATION.md``) :
    scoring concurrent borné (module 4.3) + drafting décomposé AngleAgent/
    WriterAgent (module 4.2 — seule décomposition mesurée et retenue).
    C'est l'unique composition câblée dans ``composition.py``.

    7 paramètres, 7 seams d'injection réellement distincts (pas de
    regroupement naturel comme ``PipelineConfig`` pour les autres composeurs
    — ``noqa`` assumé plutôt qu'un objet de config artificiel).

    ``timeline`` (module 4.6) est facultative : sans elle, la composition est
    identique à ce qu'elle était, et aucune étape ne prend un chemin de code
    différent. Cf. ``OBSERVABILITY.md``.

    ``usage_sink`` doit être le **même** sink que celui injecté dans
    l'``AnthropicClient`` de l'appelant : ``ConcurrentScoreStep`` s'en sert
    pour vérifier ``max_cost_usd`` entre deux lots (cf. ``CONCURRENCY.md``).
    Passer un sink différent (ou aucun) désactive silencieusement le budget
    dur — le scoring fonctionne quand même, juste sans plafond de coût.
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
    """Projette l'état final du workflow vers le contrat ``PipelineReport``
    existant (``run_report.json``, ``RunRecord`` — inchangé depuis le module
    3.3, aucune régression sur son schéma). ``n_skipped_no_angle`` (module
    4.2) n'a pas d'équivalent dans ``PipelineReport`` : cette information
    reste visible sur l'état complet / le ``WorkflowRun``, pas dupliquée ici.
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
