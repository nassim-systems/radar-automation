"""Équation de valeur humaine (module 4.6, OBSERVABILITY.md).

Ces tests portent sur l'arithmétique et sur l'**honnêteté du modèle**, pas
sur la justesse des hypothèses : aucun test ne peut valider qu'un humain met
bien 30 secondes à trier un article. Ce qui est vérifiable, et vérifié ici :
que le temps de relecture résiduel est bien déduit du gain, qu'un ratio sans
dénominateur ne se présente pas comme un grand nombre, et qu'une baseline
non mesurée s'annonce comme telle.
"""
from datetime import UTC, datetime
from pathlib import Path

from radar.observability.value import (
    HumanBaseline,
    compute_value_equation,
    load_human_baseline,
    write_human_baseline,
)
from radar.pipeline import PipelineReport

N_SCORED = 30
N_DRAFTED = 3
MACHINE_SECONDS = 60.0
MACHINE_COST_USD = 0.02

HUMAN_TRIAGE_SECONDS = 900.0  # 30 items × 30 s
HUMAN_DRAFTING_SECONDS = 1800.0  # 3 brouillons × 600 s
HUMAN_TOTAL_SECONDS = 2700.0
HUMAN_REMAINING_SECONDS = 180.0  # 3 relectures × 60 s
HUMAN_SAVED_SECONDS = 2520.0
HUMAN_COST_TOTAL_EUR = 45.0
HUMAN_COST_SAVED_EUR = 42.0
NET_SAVING_EUR = 41.98
ROI_RATIO = 2100.0
MONTHLY_HOURS_SAVED = 14.0
MONTHLY_NET_SAVING_EUR = 839.6
TIME_COMPRESSION = 45.0


def _baseline(**overrides: object) -> HumanBaseline:
    defaults: dict[str, object] = {
        "seconds_per_item_triage": 30.0,
        "seconds_per_draft": 600.0,
        "seconds_per_draft_review": 60.0,
        "hourly_cost_eur": 60.0,
        "runs_per_month": 20,
        "eur_per_usd": 1.0,
    }
    defaults.update(overrides)
    return HumanBaseline(**defaults)


def _report(*, n_scored: int = N_SCORED, n_drafted: int = N_DRAFTED) -> PipelineReport:
    return PipelineReport(
        n_fetched=57,
        n_dedup=57,
        n_fresh=n_scored,
        n_unseen=n_scored,
        n_scored=n_scored,
        n_above_threshold=n_drafted,
        n_drafted=n_drafted,
        n_llm_calls=n_scored + 2 * n_drafted,
        n_failures=0,
        drafts=[],
    )


def test_value_equation_computes_time_cost_and_roi() -> None:
    equation = compute_value_equation(
        report=_report(),
        machine_seconds=MACHINE_SECONDS,
        machine_cost_usd=MACHINE_COST_USD,
        baseline=_baseline(),
    )

    assert equation.human_seconds_triage == HUMAN_TRIAGE_SECONDS
    assert equation.human_seconds_drafting == HUMAN_DRAFTING_SECONDS
    assert equation.human_seconds_total == HUMAN_TOTAL_SECONDS
    assert equation.human_cost_total_eur == HUMAN_COST_TOTAL_EUR
    assert equation.roi_ratio == ROI_RATIO
    assert equation.time_compression_ratio == TIME_COMPRESSION


def test_review_time_is_deducted_from_the_gain_not_ignored() -> None:
    """Le système déplace le travail humain, il ne le supprime pas — la
    relecture des brouillons produits reste à la charge de l'humain."""
    equation = compute_value_equation(
        report=_report(),
        machine_seconds=MACHINE_SECONDS,
        machine_cost_usd=MACHINE_COST_USD,
        baseline=_baseline(),
    )

    assert equation.human_seconds_remaining == HUMAN_REMAINING_SECONDS
    assert equation.human_seconds_saved == HUMAN_SAVED_SECONDS
    assert equation.human_seconds_saved < equation.human_seconds_total
    assert equation.human_cost_saved_eur == HUMAN_COST_SAVED_EUR
    assert equation.net_saving_eur == NET_SAVING_EUR


def test_monthly_projection_scales_with_runs_per_month() -> None:
    equation = compute_value_equation(
        report=_report(),
        machine_seconds=MACHINE_SECONDS,
        machine_cost_usd=MACHINE_COST_USD,
        baseline=_baseline(),
    )

    assert equation.monthly_human_hours_saved == MONTHLY_HOURS_SAVED
    assert equation.monthly_net_saving_eur == MONTHLY_NET_SAVING_EUR


def test_a_run_that_drafts_nothing_produces_no_drafting_gain() -> None:
    """Comportement voulu : l'équation suit la production réelle du run,
    y compris quand elle est nulle — pas une capacité théorique."""
    equation = compute_value_equation(
        report=_report(n_drafted=0),
        machine_seconds=MACHINE_SECONDS,
        machine_cost_usd=MACHINE_COST_USD,
        baseline=_baseline(),
    )

    assert equation.human_seconds_drafting == 0
    assert equation.human_seconds_remaining == 0
    assert equation.human_seconds_saved == HUMAN_TRIAGE_SECONDS


def test_ratios_are_none_rather_than_infinite_when_undefined() -> None:
    equation = compute_value_equation(
        report=_report(),
        machine_seconds=0.0,
        machine_cost_usd=0.0,
        baseline=_baseline(),
    )

    assert equation.roi_ratio is None
    assert equation.time_compression_ratio is None


def test_default_baseline_announces_itself_as_unmeasured() -> None:
    equation = compute_value_equation(
        report=_report(), machine_seconds=MACHINE_SECONDS, machine_cost_usd=0.02
    )

    assert equation.baseline.measured is False
    assert "chronométrage" in equation.baseline.note


def test_missing_baseline_file_falls_back_to_hypotheses(tmp_path: Path) -> None:
    baseline = load_human_baseline(tmp_path / "absent.json")

    assert baseline.measured is False


def test_measured_baseline_round_trips_through_disk(tmp_path: Path) -> None:
    measured = _baseline(measured=True, measured_at=datetime.now(tz=UTC))
    out = tmp_path / "human_baseline.json"

    write_human_baseline(measured, out)
    reloaded = load_human_baseline(out)

    assert reloaded.measured is True
    assert reloaded.seconds_per_item_triage == measured.seconds_per_item_triage
    assert reloaded.measured_at is not None
