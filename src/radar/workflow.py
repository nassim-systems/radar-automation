"""Le pipeline radar exprimé comme un ``Workflow`` (module 4.1) — avec la
variante décomposée AngleAgent + WriterAgent (module 4.2, retenue après
mesure : voir ``ANGLE_AGENT.md``) et un ``ScoreStep`` concurrent borné
(module 4.3 : voir ``CONCURRENCY.md``).

Ne réimplémente AUCUNE logique : chaque ``Step`` délègue à la même fonction
pure que ``run_pipeline`` (``radar/pipeline.py``) utilise déjà —
``deduplicate``, ``filter_fresh``, ``filter_unseen``, ``score_item``,
``filter_by_min_score``, ``select_top_k``, ``build_draft_prompt``/
``parse_draft`` (mono-appel), ``decide_angle``/``write_draft`` (décomposé),
``score_items_concurrently`` (concurrent). ``run_pipeline`` n'est pas
modifié et reste le chemin de production (``composition.py``) : ce module
est une démonstration parallèle de l'abstraction ``core.workflow``, pas un
remplacement. Voir ``WORKFLOW.md``.
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
from radar.pipeline import PipelineConfig, ScoredDraft, filter_by_min_score
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

    def __init__(self, llm: LLMClient, config: PipelineConfig) -> None:
        self._llm = llm
        self._config = config

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        scored = [
            ScoredItem(item=item, score=score_item(item, self._llm).score)
            for item in s.unseen[: self._config.max_scored]
        ]
        return s.model_copy(update={"scored": scored})


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
    ) -> None:
        self._llm = llm
        self._pipeline_config = pipeline_config
        self._concurrency_config = concurrency_config
        self._usage_sink = usage_sink

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        candidates = s.unseen[: self._pipeline_config.max_scored]
        report = score_items_concurrently(
            candidates,
            self._llm,
            config=self._concurrency_config,
            usage_sink=self._usage_sink,
        )
        return s.model_copy(
            update={
                "scored": report.scored,
                "n_failures": s.n_failures + report.n_failures,
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

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        drafts: list[ScoredDraft] = []
        n_failures = 0
        for entry in s.top_k:
            prompt = build_draft_prompt(entry.item)
            try:
                response = self._llm.complete(prompt)
            except Exception:
                n_failures += 1
                continue
            draft = parse_draft(response)
            drafts.append(ScoredDraft(item=entry.item, score=entry.score, draft=draft))
        return s.model_copy(update={"drafts": drafts, "n_failures": n_failures})


class AngleStep:
    """Décide l'angle éditorial de chaque item du top-k (module 4.2).

    ``Angle.has_angle=False`` est une issue légitime, pas un échec : c'est
    précisément ce qui manquait au mono-appel ``DraftStep``, qui rédige
    toujours quelque chose même quand aucun angle PME honnête n'existe. Voir
    ``ANGLE_AGENT.md`` pour la mesure ayant motivé ce choix."""

    name = "angle"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        angled = [(entry, decide_angle(entry.item, self._llm)) for entry in s.top_k]
        return s.model_copy(update={"angled": angled})


class WriteStep:
    """Rédige uniquement les items avec un angle retenu par ``AngleStep`` —
    remplace ``DraftStep`` dans la composition décomposée. Même isolation
    des échecs LLM item par item que ``DraftStep``."""

    name = "write"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def run(self, state: WorkflowState) -> WorkflowState:
        s = _as_radar_state(state)
        drafts: list[ScoredDraft] = []
        n_failures = 0
        n_skipped = 0
        for entry, angle in s.angled:
            if not angle.has_angle:
                n_skipped += 1
                continue
            try:
                draft = write_draft(entry.item, angle, self._llm)
            except Exception:
                n_failures += 1
                continue
            drafts.append(ScoredDraft(item=entry.item, score=entry.score, draft=draft))
        return s.model_copy(
            update={
                "drafts": drafts,
                "n_failures": s.n_failures + n_failures,
                "n_skipped_no_angle": n_skipped,
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
) -> list[Step]:
    """Câble les 9 étapes du radar dans l'ordre de ``run_pipeline``.

    Pure composition — aucune des étapes n'est instanciée différemment de ce
    que ``composition.py::build_radar_pipeline`` câble déjà pour
    ``run_pipeline`` (même ``PipelineConfig``, pas de champs dupliqués). Un
    appelant qui veut un workflow différent (ex. un dry-run sans drafting,
    ou sans persistance) recompose sa propre liste à partir des mêmes
    classes plutôt que de dupliquer cette fonction.
    """
    return [
        FetchStep(fetch_items),
        DeduplicateStep(),
        FilterFreshStep(config),
        FilterUnseenStep(seen_store),
        ScoreStep(llm, config),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        DraftStep(llm),
        MarkSeenStep(seen_store),
    ]


def build_radar_steps_decomposed(
    *,
    fetch_items: Callable[[], list[RawItem]],
    seen_store: SeenStore,
    llm: LLMClient,
    config: PipelineConfig,
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
        ScoreStep(llm, config),
        FilterByMinScoreStep(config),
        SelectTopKStep(config),
        AngleStep(llm),
        WriteStep(llm),
        MarkSeenStep(seen_store),
    ]
