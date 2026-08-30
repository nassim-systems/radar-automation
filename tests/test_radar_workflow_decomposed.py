from datetime import UTC, datetime, timedelta

from core.usage import ListUsageSink, LlmUsage
from core.workflow.engine import run_workflow
from radar.domain import RawItem
from radar.pipeline import PipelineConfig
from radar.tools.seen_store import InMemorySeenStore
from radar.workflow import RadarWorkflowState, build_radar_steps_decomposed

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
MAX_AGE = timedelta(days=7)

N_ITEMS_WITH_ANGLE_DECISION = 2

EXPECTED_DECOMPOSED_STEP_NAMES = [
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


class _AngleThenWriteLLM:
    """Distingue la frontière LLM de l'AngleAgent de celle du WriterAgent
    par un marqueur unique à chaque prompt (cf. angle.py / writer.py) —
    permet de scénariser un angle différent par item avec un seul LLM."""

    def __init__(self, angle_for_title: dict[str, str], draft_text: str) -> None:
        self._angle_for_title = angle_for_title
        self._draft_text = draft_text

    def complete(self, prompt: str) -> str:
        if "rédige un court brouillon de post" in prompt:
            return self._draft_text
        for title, response in self._angle_for_title.items():
            if title in prompt:
                return response
        return "ANGLE: AUCUN"


def _item(external_id: str, title: str) -> RawItem:
    return RawItem(
        source="rss",
        external_id=external_id,
        title=title,
        url="",
        published_at=FRESH,
        summary="résumé",
    )


def _config() -> PipelineConfig:
    return PipelineConfig(now=NOW, max_age=MAX_AGE, k=5, max_scored=10, min_score=0)


def test_build_radar_steps_decomposed_has_expected_order() -> None:
    steps = build_radar_steps_decomposed(
        fetch_items=lambda: [],
        seen_store=InMemorySeenStore(),
        llm=_AngleThenWriteLLM({}, draft_text="texte"),
        config=_config(),
    )

    assert [step.name for step in steps] == EXPECTED_DECOMPOSED_STEP_NAMES


def test_decomposed_workflow_skips_items_without_a_genuine_angle() -> None:
    items = [
        _item("1", "Automatiser sa facturation"),
        _item("2", "Nouvelle levée de fonds sans lien PME"),
    ]
    llm = _AngleThenWriteLLM(
        angle_for_title={"Automatiser sa facturation": "ANGLE: Gagner du temps"},
        draft_text="Brouillon rédigé.",
    )
    steps = build_radar_steps_decomposed(
        fetch_items=lambda: list(items),
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(),
    )

    run = run_workflow(steps, RadarWorkflowState())
    state = run.final_state
    assert isinstance(state, RadarWorkflowState)

    assert len(state.angled) == N_ITEMS_WITH_ANGLE_DECISION
    assert len(state.drafts) == 1  # un seul avait un angle honnête
    assert state.drafts[0].item.external_id == "1"
    assert state.n_skipped_no_angle == 1


def test_decomposed_workflow_only_marks_drafted_items_as_seen() -> None:
    # Un item sans angle reste "à voir" : comme un échec de draft, il sera
    # retenté au run suivant plutôt que d'être marqué vu à tort.
    items = [
        _item("1", "Automatiser sa facturation"),
        _item("2", "Nouvelle levée de fonds sans lien PME"),
    ]
    seen_store = InMemorySeenStore()
    llm = _AngleThenWriteLLM(
        angle_for_title={"Automatiser sa facturation": "ANGLE: Gagner du temps"},
        draft_text="Brouillon rédigé.",
    )
    steps = build_radar_steps_decomposed(
        fetch_items=lambda: list(items),
        seen_store=seen_store,
        llm=llm,
        config=_config(),
    )

    run_workflow(steps, RadarWorkflowState())

    assert seen_store.load_seen() == {"rss:1"}


def test_decomposed_workflow_captures_usage_across_angle_and_write() -> None:
    class _UsageReportingLLM(_AngleThenWriteLLM):
        def __init__(self, sink: ListUsageSink, per_call: LlmUsage) -> None:
            super().__init__(
                angle_for_title={"Alpha": "ANGLE: Un angle honnête"},
                draft_text="Brouillon.",
            )
            self._sink = sink
            self._per_call = per_call

        def complete(self, prompt: str) -> str:
            self._sink.record(self._per_call)
            return super().complete(prompt)

    sink = ListUsageSink()
    per_call = LlmUsage(input_tokens=10, output_tokens=1, cost_usd=0.001)
    llm = _UsageReportingLLM(sink, per_call)
    steps = build_radar_steps_decomposed(
        fetch_items=lambda: [_item("1", "Alpha")],
        seen_store=InMemorySeenStore(),
        llm=llm,
        config=_config(),
    )

    run = run_workflow(steps, RadarWorkflowState(), usage_sink=sink)

    # 1 appel score + 1 appel angle + 1 appel write (angle retenu) -> x3.
    assert run.usage == LlmUsage(input_tokens=30, output_tokens=3, cost_usd=0.003)
