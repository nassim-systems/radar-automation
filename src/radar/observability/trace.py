"""Trace de run exportable (module 4.6) — l'observabilité déjà produite,
rendue lisible hors du processus.

**Pourquoi un fichier dédié plutôt que des champs de plus dans
``run_report.json``.** ``MIGRATION.md`` §5 pose une non-régression explicite :
le schéma de ``PipelineReport`` est inchangé, et c'est ce qui a rendu la
migration du module 4.5 vérifiable. ``RunRecord`` (donc ``run_history.json``)
en dépend directement. Y greffer la trace romprait cette garantie pour une
raison purement cosmétique. ``run_trace.json`` est donc un second artefact,
apparié au premier par ``run_at`` — un contrat de plus, aucun contrat cassé.

**Rien n'est mesuré ici.** Ce module ne fait qu'agréger : les durées par
étape viennent de ``run_workflow`` (module 4.1), les appels de la
``CallTimeline`` (module 4.6), les tokens et coûts du ``UsageSink`` (module
3.4). Les vues « par phase » et « par item » sont des projections de la même
source d'appels — pas des compteurs parallèles susceptibles de diverger.
"""
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from core.usage import LlmUsage
from core.workflow.models import StepTrace, WorkflowRun
from radar.llm.timing import CallSubject, LlmCallRecord
from radar.observability.models import RunRecord
from radar.observability.value import ValueEquation
from radar.pipeline import PipelineReport


class RunCounters(BaseModel):
    """Les compteurs de ``PipelineReport``, sans les brouillons.

    Les brouillons restent dans ``run_report.json`` : les dupliquer ici
    doublerait la taille du fichier et créerait deux copies à garder
    cohérentes pour zéro information nouvelle.
    """

    n_fetched: int
    n_dedup: int
    n_fresh: int
    n_unseen: int
    n_scored: int
    n_above_threshold: int
    n_drafted: int
    n_llm_calls: int
    n_failures: int


class PhaseTiming(BaseModel):
    """Agrégat des appels LLM d'une phase.

    Le nom d'une phase est, par construction, le nom de l'étape qui l'émet
    (``score``, ``angle``, ``write``) : c'est ce qui permet de rapprocher le
    temps *cumulé* des appels du temps *réel* de l'étape. Leur rapport
    (``speedup``) est la mesure directe du gain de concurrence du module 4.3 —
    à 1,0 l'étape est séquentielle, au-dessus elle recouvre ses appels.
    """

    phase: str
    n_calls: int
    n_failures: int
    cumulative_seconds: float
    mean_seconds: float
    max_seconds: float
    step_wall_seconds: float | None = None
    speedup: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ItemTiming(BaseModel):
    """Ce qu'un item aura coûté en temps et en argent, tous appels confondus."""

    subject: CallSubject
    n_calls: int
    phases: list[str]
    total_seconds: float
    cost_usd: float
    ok: bool


class LatencySummary(BaseModel):
    """Latences du run, du plus global au plus fin.

    ``orchestration_seconds`` est l'écart entre la durée réelle du run et la
    somme des étapes — le coût propre du moteur. Le garder explicite évite la
    tentation de présenter la somme des étapes comme la durée du run.
    ``llm_cumulative_seconds`` peut dépasser ``run_seconds`` : c'est attendu
    dès qu'il y a de la concurrence, et c'est précisément ce que mesure
    ``PhaseTiming.speedup``.
    """

    run_seconds: float
    steps_seconds: float
    orchestration_seconds: float
    llm_cumulative_seconds: float
    llm_mean_call_seconds: float | None
    llm_slowest_call_seconds: float | None
    slowest_step: str | None
    slowest_step_seconds: float | None


class RunTrace(BaseModel):
    """Trace complète et autoportante d'un run.

    ``n_llm_calls_traced`` est mesuré indépendamment de
    ``counters.n_llm_calls`` (reconstruit par les étapes, module 4.5) : les
    deux doivent coïncider, et les avoir obtenus par deux chemins distincts
    est ce qui permet de voir un écart s'il apparaît.
    """

    run_at: datetime
    started_at: datetime
    ended_at: datetime
    counters: RunCounters
    latency: LatencySummary
    usage: LlmUsage
    n_llm_calls_traced: int
    steps: list[StepTrace] = Field(default_factory=list)
    phases: list[PhaseTiming] = Field(default_factory=list)
    items: list[ItemTiming] = Field(default_factory=list)
    calls: list[LlmCallRecord] = Field(default_factory=list)
    value: ValueEquation | None = None


class RadarRunOutcome(BaseModel):
    """Ce que renvoie le runner de production : le ``RunRecord`` historisé
    (schéma inchangé, module 3.4) **et** la trace du même run.

    Deux objets plutôt qu'un ``RunRecord`` enrichi : l'historique persistant
    garde exactement le schéma qu'il avait, et la trace reste facultative
    pour tout appelant qui ne la consomme pas.
    """

    record: RunRecord
    trace: RunTrace


def summarize_phases(
    calls: list[LlmCallRecord], steps: list[StepTrace]
) -> list[PhaseTiming]:
    """Agrège les appels par phase, en les rapprochant de l'étape homonyme."""
    wall_by_step = {step.name: step.duration_seconds for step in steps}
    order: list[str] = []
    grouped: dict[str, list[LlmCallRecord]] = {}
    for call in calls:
        if call.phase not in grouped:
            grouped[call.phase] = []
            order.append(call.phase)
        grouped[call.phase].append(call)

    phases: list[PhaseTiming] = []
    for name in order:
        group = grouped[name]
        durations = [call.duration_seconds for call in group]
        cumulative = sum(durations)
        wall = wall_by_step.get(name)
        phases.append(
            PhaseTiming(
                phase=name,
                n_calls=len(group),
                n_failures=sum(1 for call in group if not call.ok),
                cumulative_seconds=round(cumulative, 3),
                mean_seconds=round(cumulative / len(group), 3),
                max_seconds=round(max(durations), 3),
                step_wall_seconds=None if wall is None else round(wall, 3),
                speedup=(
                    round(cumulative / wall, 2)
                    if wall is not None and wall > 0
                    else None
                ),
                input_tokens=sum(call.input_tokens or 0 for call in group),
                output_tokens=sum(call.output_tokens or 0 for call in group),
                cost_usd=round(sum(call.cost_usd or 0.0 for call in group), 6),
            )
        )
    return phases


def summarize_items(calls: list[LlmCallRecord]) -> list[ItemTiming]:
    """Agrège les appels par item, dans l'ordre de leur premier appel.

    Les appels sans sujet (aucun item attaché) sont ignorés plutôt que
    regroupés sous une clé fourre-tout : ils restent visibles dans ``calls``
    et dans ``phases``, où ils ont un sens.
    """
    order: list[str] = []
    grouped: dict[str, list[LlmCallRecord]] = {}
    subjects: dict[str, CallSubject] = {}
    for call in calls:
        if call.subject is None:
            continue
        key = call.subject.key
        if key not in grouped:
            grouped[key] = []
            subjects[key] = call.subject
            order.append(key)
        grouped[key].append(call)

    return [
        ItemTiming(
            subject=subjects[key],
            n_calls=len(grouped[key]),
            phases=list(dict.fromkeys(call.phase for call in grouped[key])),
            total_seconds=round(
                sum(call.duration_seconds for call in grouped[key]), 3
            ),
            cost_usd=round(sum(call.cost_usd or 0.0 for call in grouped[key]), 6),
            ok=all(call.ok for call in grouped[key]),
        )
        for key in order
    ]


def build_run_trace(
    *,
    report: PipelineReport,
    workflow_run: WorkflowRun,
    calls: list[LlmCallRecord],
    run_at: datetime,
) -> RunTrace:
    """Assemble la trace exportable à partir des sources déjà instrumentées."""
    steps = workflow_run.trace
    steps_seconds = sum(step.duration_seconds for step in steps)
    durations = [call.duration_seconds for call in calls]
    cumulative = sum(durations)
    slowest = max(steps, key=lambda step: step.duration_seconds, default=None)

    latency = LatencySummary(
        run_seconds=round(workflow_run.duration_seconds, 3),
        steps_seconds=round(steps_seconds, 3),
        orchestration_seconds=round(
            workflow_run.duration_seconds - steps_seconds, 4
        ),
        llm_cumulative_seconds=round(cumulative, 3),
        llm_mean_call_seconds=(
            round(cumulative / len(durations), 3) if durations else None
        ),
        llm_slowest_call_seconds=round(max(durations), 3) if durations else None,
        slowest_step=None if slowest is None else slowest.name,
        slowest_step_seconds=(
            None if slowest is None else round(slowest.duration_seconds, 3)
        ),
    )

    return RunTrace(
        run_at=run_at,
        started_at=workflow_run.started_at,
        ended_at=workflow_run.ended_at,
        counters=RunCounters(**report.model_dump(exclude={"drafts"})),
        latency=latency,
        usage=workflow_run.usage,
        n_llm_calls_traced=len(calls),
        steps=steps,
        phases=summarize_phases(calls, steps),
        items=summarize_items(calls),
        calls=calls,
    )


def write_trace_json(trace: RunTrace, out: str | Path) -> None:
    """Écrit la trace en JSON, UTF-8 explicite — même convention que
    ``write_report_json`` (indépendance vis-à-vis des redirections shell)."""
    Path(out).write_text(
        json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
