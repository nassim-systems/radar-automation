"""Le chemin de production unique (module 4.5) : ``build_radar_steps_production``
(scoring concurrent + drafting décomposé). Voir ``MIGRATION.md``.
"""
from datetime import UTC, datetime, timedelta

from core.usage import ListUsageSink
from core.workflow.engine import run_workflow
from radar.concurrent_scoring import ConcurrentScoringConfig
from radar.domain import RawItem
from radar.pipeline import PipelineConfig, PipelineReport
from radar.tools.seen_store import InMemorySeenStore
from radar.workflow import (
    RadarWorkflowState,
    build_radar_steps_production,
    radar_workflow_state_to_pipeline_report,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
MAX_AGE = timedelta(days=7)
MIN_SCORE = 8  # même seuil calibré qu'en production (composition.py)
N_ITEMS = 2
N_LLM_CALLS = 4  # 2 scoring + 1 angle + 1 write

EXPECTED_PRODUCTION_STEP_NAMES = [
    "fetch",
    "deduplicate",
    "filter_fresh",
    "filter_unseen",
    "score",
    "filter_by_min_score",
    "select_top_k",
    "angle",
    "write",
    "mark_seen",
]


class _ScriptedProductionLLM:
    """Distingue scoring / angle / rédaction par un marqueur unique à
    chaque prompt (cf. radar/scoring.py, radar/drafting/angle.py,
    radar/drafting/writer.py) — score piloté par item, angle toujours
    honnête, rédaction canned."""

    def __init__(self, score_by_title: dict[str, str], draft_text: str) -> None:
        self._score_by_title = score_by_title
        self._draft_text = draft_text

    def complete(self, prompt: str) -> str:
        if "rédige un court brouillon de post" in prompt:
            return self._draft_text
        if "ANGLE:" in prompt and "identifier l'angle éditorial" in prompt:
            return "ANGLE: Un angle honnête et concret pour une PME"
        for title, score in self._score_by_title.items():
            if title in prompt:
                return score
        raise AssertionError(f"prompt inattendu : {prompt[:200]}")


def _item(external_id: str, title: str) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=FRESH,
        summary="résumé",
    )


def _config(*, min_score: int = MIN_SCORE) -> PipelineConfig:
    return PipelineConfig(
        now=NOW, max_age=MAX_AGE, k=5, max_scored=10, min_score=min_score
    )


def test_build_radar_steps_production_has_expected_order() -> None:
    steps = build_radar_steps_production(
        fetch_items=lambda: [],
        seen_store=InMemorySeenStore(),
        llm=_ScriptedProductionLLM({}, draft_text="texte"),
        config=_config(),
    )

    assert [step.name for step in steps] == EXPECTED_PRODUCTION_STEP_NAMES


def test_production_workflow_respects_min_score() -> None:
    items = [_item("1", "SousLeSeuil"), _item("2", "AuDessusDuSeuil")]
    llm = _ScriptedProductionLLM(
        {"SousLeSeuil": "6", "AuDessusDuSeuil": "9"}, draft_text="Brouillon."
    )
    steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(min_score=MIN_SCORE),
    )

    run = run_workflow(steps, RadarWorkflowState())
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)

    assert len(state.scored) == N_ITEMS
    assert [s.item.external_id for s in state.above_threshold] == ["2"]
    assert [d.item.external_id for d in state.drafts] == ["2"]


def test_production_workflow_is_idempotent_across_two_runs() -> None:
    items = [_item("1", "Alpha"), _item("2", "Beta")]
    seen_store = InMemorySeenStore()
    llm = _ScriptedProductionLLM(
        {"Alpha": "9", "Beta": "9"}, draft_text="Brouillon."
    )

    first_steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=seen_store,
        llm=llm,
        config=_config(),
    )
    first = run_workflow(first_steps, RadarWorkflowState())
    first_state = first.final_state
    assert isinstance(first_state, RadarWorkflowState)
    assert len(first_state.drafts) == N_ITEMS

    second_steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=seen_store,
        llm=llm,
        config=_config(),
    )
    second = run_workflow(second_steps, RadarWorkflowState())
    second_state = second.final_state
    assert isinstance(second_state, RadarWorkflowState)

    assert second_state.unseen == []
    assert second_state.scored == []
    assert second_state.drafts == []


def test_radar_workflow_state_to_pipeline_report_maps_all_fields() -> None:
    items = [_item("1", "Alpha"), _item("2", "Beta")]
    llm = _ScriptedProductionLLM(
        {"Alpha": "9", "Beta": "3"}, draft_text="Brouillon."
    )
    steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(),
    )

    run = run_workflow(steps, RadarWorkflowState())

    report = radar_workflow_state_to_pipeline_report(run.final_state)
    assert isinstance(report, PipelineReport)
    assert report.n_fetched == N_ITEMS
    assert report.n_dedup == N_ITEMS
    assert report.n_fresh == N_ITEMS
    assert report.n_unseen == N_ITEMS
    assert report.n_scored == N_ITEMS
    assert report.n_above_threshold == 1  # seul "Alpha" (score 9) passe min_score=8
    assert report.n_drafted == 1
    assert report.n_failures == 0
    assert report.n_llm_calls == N_LLM_CALLS


def test_production_workflow_produces_a_complete_workflow_run() -> None:
    """Vérifie que le WorkflowRun produit par la composition de production
    est complet : trace des 10 étapes avec durées, usage agrégé, brouillons
    dans l'état final — cf. livrable du module 4.5."""
    items = [_item("1", "Alpha")]
    sink = ListUsageSink()
    llm = _ScriptedProductionLLM({"Alpha": "9"}, draft_text="Brouillon complet.")
    steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(),
        concurrency_config=ConcurrentScoringConfig(max_concurrency=5),
        usage_sink=sink,
    )

    run = run_workflow(steps, RadarWorkflowState(), usage_sink=sink)

    assert [t.name for t in run.trace] == EXPECTED_PRODUCTION_STEP_NAMES
    assert len(run.trace) == len(EXPECTED_PRODUCTION_STEP_NAMES)
    assert all(t.ok for t in run.trace)
    assert all(t.duration_seconds >= 0 for t in run.trace)
    assert run.usage is not None  # FakeLLM ne rapporte rien : coût à 0, mais présent
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)
    assert len(state.drafts) == 1
    assert state.drafts[0].draft.text == "Brouillon complet."


def test_angle_step_isolates_a_failing_item_instead_of_aborting_the_run() -> None:
    """Durcissement production (4.5) : une erreur LLM sur la décision
    d'angle d'un item n'abat pas les autres — cf. AngleStep."""

    class _FailsOnBetaAngle:
        def complete(self, prompt: str) -> str:
            if "identifier l'angle éditorial" in prompt and "Beta" in prompt:
                raise RuntimeError("panne simulée")
            if "rédige un court brouillon de post" in prompt:
                return "Brouillon."
            if "ANGLE:" in prompt:
                return "ANGLE: Un angle honnête"
            return "9"

    items = [_item("1", "Alpha"), _item("2", "Beta")]
    steps = build_radar_steps_production(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=_FailsOnBetaAngle(),
        config=_config(),
    )

    run = run_workflow(steps, RadarWorkflowState())
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)

    assert [d.item.external_id for d in state.drafts] == ["1"]
    assert state.n_failures == 1
