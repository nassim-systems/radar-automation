"""Types et fonctions pures partagés par le pipeline radar.

``run_pipeline`` (la fonction monolithique séquentielle du module 1.x) a été
supprimée au module 4.5 : ``radar/workflow.py`` (``build_radar_steps_production``,
scoring concurrent + drafting décomposé) est désormais l'unique chemin de
production, câblé dans ``composition.py``. Voir ``MIGRATION.md`` pour
l'arbitrage. Ce module conserve les types et fonctions pures que le workflow
réutilise : ``PipelineConfig``, ``PipelineReport``, ``ScoredDraft``,
``filter_by_min_score``, ``write_report_json``.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from radar.decision.models import ScoredItem
from radar.domain import RawItem
from radar.drafting.parse import Draft


class PipelineConfig(BaseModel):
    now: datetime
    max_age: timedelta
    k: int
    max_scored: int
    min_score: int = 0


class ScoredDraft(BaseModel):
    """Un brouillon apparié à son item et à son score (pas de liste positionnelle)."""

    item: RawItem
    score: int
    draft: Draft


class PipelineReport(BaseModel):
    n_fetched: int
    n_dedup: int
    n_fresh: int
    n_unseen: int
    n_scored: int
    n_above_threshold: int
    n_drafted: int
    n_llm_calls: int
    n_failures: int
    drafts: list[ScoredDraft]


def filter_by_min_score(items: list[ScoredItem], min_score: int) -> list[ScoredItem]:
    """Ne garde que les items dont le score atteint ``min_score``.

    Étage pur, appliqué avant ``select_top_k`` : un item hors-sujet ne doit
    pas consommer une place dans le top-K à la place d'un item pertinent.
    """
    return [scored for scored in items if scored.score >= min_score]


def write_report_json(report: PipelineReport, out: str | Path) -> None:
    """Écrit ``report`` en JSON, encoding UTF-8 explicite.

    Indépendant de toute redirection shell (celle-ci varie d'encodage par OS).
    """
    Path(out).write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
