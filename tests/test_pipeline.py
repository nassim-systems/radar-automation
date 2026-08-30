"""Fonctions et types purs survivants de ``run_pipeline`` (supprimée au
module 4.5 — voir ``MIGRATION.md``). Le comportement du pipeline complet
(fetch → ... → mark_seen, idempotence, isolation des échecs, seuil) est
désormais testé au niveau du workflow de production :
``tests/test_radar_workflow_production.py``.
"""
from datetime import UTC, datetime
from pathlib import Path

from radar.decision.models import ScoredItem
from radar.domain import RawItem
from radar.drafting.parse import Draft
from radar.pipeline import (
    PipelineReport,
    ScoredDraft,
    filter_by_min_score,
    write_report_json,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _scored_item(external_id: str, score: int) -> ScoredItem:
    return ScoredItem(
        item=RawItem(
            source="rss",
            external_id=external_id,
            title="Titre",
            url="",
            published_at=NOW,
            summary="résumé",
        ),
        score=score,
    )


def test_filter_by_min_score_keeps_items_at_or_above_threshold() -> None:
    items = [_scored_item("1", 5), _scored_item("2", 8), _scored_item("3", 10)]

    result = filter_by_min_score(items, min_score=8)

    assert {i.item.external_id for i in result} == {"2", "3"}


def test_filter_by_min_score_excludes_items_below_threshold() -> None:
    items = [_scored_item("1", 3), _scored_item("2", 5)]

    assert filter_by_min_score(items, min_score=6) == []


def test_filter_by_min_score_is_pure() -> None:
    items = [_scored_item("1", 5)]
    original = list(items)

    filter_by_min_score(items, min_score=6)

    assert items == original


def _report_with_accented_draft(title: str) -> PipelineReport:
    item = RawItem(
        source="rss",
        external_id="1",
        title=title,
        url="",
        published_at=NOW,
        summary="résumé",
    )
    draft = ScoredDraft(item=item, score=7, draft=Draft(text=f"Brouillon : {title}"))
    return PipelineReport(
        n_fetched=1,
        n_dedup=1,
        n_fresh=1,
        n_unseen=1,
        n_scored=1,
        n_above_threshold=1,
        n_drafted=1,
        n_llm_calls=1,
        n_failures=0,
        drafts=[draft],
    )


def test_pipeline_report_survives_utf8_round_trip(tmp_path: Path) -> None:
    """Non-régression : les accents ne doivent pas se corrompre à l'écriture.

    ``r├®seau`` est la mojibake caractéristique d'un octet UTF-8 relu avec un
    codepage Windows (cp850/cp1252) — le symptôme exact du bug corrigé par
    l'écriture UTF-8 explicite de ``write_report_json``.
    """
    report = _report_with_accented_draft("Le réseau électrique sous tension")

    out = tmp_path / "run_report.json"
    write_report_json(report, out)
    contenu = out.read_text(encoding="utf-8")

    assert "réseau" in contenu
    assert "r├®seau" not in contenu
