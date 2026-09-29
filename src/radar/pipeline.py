"""Types and pure functions shared by the radar pipeline.

``run_pipeline`` (the sequential monolithic function of module 1.x) was
removed in module 4.5: ``radar/workflow.py`` (``build_radar_steps_production``,
concurrent scoring + decomposed drafting) is now the only production
path, wired in ``composition.py``. See ``MIGRATION.md`` for the
trade-off. This module keeps the pure types and functions the workflow
reuses: ``PipelineConfig``, ``PipelineReport``, ``ScoredDraft``,
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
    """A draft paired with its item and its score (no positional list)."""

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
    """Keep only the items whose score reaches ``min_score``.

    Pure stage, applied before ``select_top_k``: an off-topic item must not
    take a top-K slot away from a relevant item.
    """
    return [scored for scored in items if scored.score >= min_score]


def write_report_json(report: PipelineReport, out: str | Path) -> None:
    """Write ``report`` as JSON with explicit UTF-8 encoding.

    Independent of any shell redirection (whose encoding varies by OS).
    """
    Path(out).write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
