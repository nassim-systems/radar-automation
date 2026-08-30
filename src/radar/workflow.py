"""Le pipeline radar exprimé comme un ``Workflow`` (module 4.1).

Ne réimplémente AUCUNE logique : chaque ``Step`` délègue à la même fonction
pure que ``run_pipeline`` (``radar/pipeline.py``) utilise déjà —
``deduplicate``, ``filter_fresh``, ``filter_unseen``, ``score_item``,
``filter_by_min_score``, ``select_top_k``, ``build_draft_prompt``/
``parse_draft``. ``run_pipeline`` n'est pas modifié et reste le chemin de
production (``composition.py``) : ce module est une démonstration parallèle
de l'abstraction ``core.workflow``, pas un remplacement. Voir ``WORKFLOW.md``.
"""
from collections.abc import Callable

from pydantic import Field

from core.workflow.engine import Step
from core.workflow.models import WorkflowState
from radar.decision.models import ScoredItem
from radar.decision.select_top_k import select_top_k
from radar.domain import RawItem
from radar.drafting.parse import parse_draft
from radar.drafting.prompt import build_draft_prompt
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
    drafts: list[ScoredDraft] = Field(default_factory=list)
    n_failures: int = 0


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
