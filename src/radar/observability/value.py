"""Human value equation (module 4.6): human time replaced, equivalent cost,
ROI projection.

**Epistemic status of this module: read before using its figures.**
Everything else in this project is *measured*: scores come from an annotated
held-out set, costs from the SDK, latencies from a clock. Not here. A value
equation rests on **human parameters** (how long a person takes to triage an
article, to write a post, what their hour costs) that this repo cannot
measure on its own.

The separation is therefore explicit and encoded in the type:
``HumanBaseline`` holds the *assumptions*, ``ValueEquation`` the *calculation*,
and ``HumanBaseline.measured`` says whether the parameters come from a
real timing run (``scripts/measure_human_baseline.py``) or from the defaults
below. An ROI figure with ``measured`` set to ``False`` is a parametric
projection, not a result, and must be presented as such.

The defaults are not measurements in disguise: they are conservative orders
of magnitude, chosen to be replaced.
"""
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from radar.pipeline import PipelineReport

SECONDS_PER_HOUR = 3600.0

_DEFAULT_NOTE = (
    "Valeurs par défaut non mesurées — ordres de grandeur à remplacer par un "
    "chronométrage réel (scripts/measure_human_baseline.py)."
)


class HumanBaseline(BaseModel):
    """Parameters of the human work that the radar replaces or lightens.

    ``seconds_per_draft_review`` is the honesty point of this model: the
    system does not remove human work, it moves it. A produced draft must still
    be reviewed and approved; this residual time is deducted from the gain,
    never ignored. Without this term, the equation would systematically
    overestimate the gain.
    """

    seconds_per_item_triage: float = 25.0
    seconds_per_draft: float = 480.0
    seconds_per_draft_review: float = 45.0
    hourly_cost_eur: float = 50.0
    runs_per_month: int = 21
    eur_per_usd: float = 0.92
    measured: bool = False
    measured_at: datetime | None = None
    note: str = _DEFAULT_NOTE


class ValueEquation(BaseModel):
    """Result of the computation, with its assumptions attached.

    ``baseline`` is embedded on purpose: an ROI figure separated from its
    parameters cannot be interpreted and, worse, can be reused out of context.
    """

    baseline: HumanBaseline

    n_items_triaged: int
    n_drafts: int

    human_seconds_triage: float
    human_seconds_drafting: float
    human_seconds_total: float
    human_seconds_remaining: float
    human_seconds_saved: float

    machine_seconds: float
    time_compression_ratio: float | None

    human_cost_total_eur: float
    human_cost_saved_eur: float
    machine_cost_usd: float
    machine_cost_eur: float
    net_saving_eur: float
    roi_ratio: float | None

    monthly_human_hours_saved: float
    monthly_machine_cost_eur: float
    monthly_net_saving_eur: float


def _round(value: float, digits: int) -> float:
    return round(value, digits)


def compute_value_equation(
    *,
    report: PipelineReport,
    machine_seconds: float,
    machine_cost_usd: float,
    baseline: HumanBaseline | None = None,
) -> ValueEquation:
    """Apply ``baseline`` to the actual counters of a run.

    The volume of human work replaced is indexed on what the system
    *actually* did in that run (``n_scored`` items triaged, ``n_drafted``
    drafts written), not on a theoretical capacity. A run that drafts
    nothing therefore yields zero writing gain, which is the intended
    behavior: the equation tracks real output, even when it is
    low.

    ``roi_ratio`` and ``time_compression_ratio`` are ``None`` rather than
    infinity when their denominator is zero: an uncomputable ratio must not
    present itself as a very large number.
    """
    params = baseline if baseline is not None else HumanBaseline()

    n_items = report.n_scored
    n_drafts = report.n_drafted

    triage = n_items * params.seconds_per_item_triage
    drafting = n_drafts * params.seconds_per_draft
    total = triage + drafting
    remaining = n_drafts * params.seconds_per_draft_review
    saved = total - remaining

    cost_per_second = params.hourly_cost_eur / SECONDS_PER_HOUR
    human_cost_total = total * cost_per_second
    human_cost_saved = saved * cost_per_second
    machine_cost_eur = machine_cost_usd * params.eur_per_usd
    net_saving = human_cost_saved - machine_cost_eur

    return ValueEquation(
        baseline=params,
        n_items_triaged=n_items,
        n_drafts=n_drafts,
        human_seconds_triage=_round(triage, 1),
        human_seconds_drafting=_round(drafting, 1),
        human_seconds_total=_round(total, 1),
        human_seconds_remaining=_round(remaining, 1),
        human_seconds_saved=_round(saved, 1),
        machine_seconds=_round(machine_seconds, 3),
        time_compression_ratio=(
            _round(total / machine_seconds, 2) if machine_seconds > 0 else None
        ),
        human_cost_total_eur=_round(human_cost_total, 2),
        human_cost_saved_eur=_round(human_cost_saved, 2),
        machine_cost_usd=_round(machine_cost_usd, 6),
        machine_cost_eur=_round(machine_cost_eur, 6),
        net_saving_eur=_round(net_saving, 2),
        roi_ratio=(
            _round(human_cost_saved / machine_cost_eur, 1)
            if machine_cost_eur > 0
            else None
        ),
        monthly_human_hours_saved=_round(
            saved * params.runs_per_month / SECONDS_PER_HOUR, 2
        ),
        monthly_machine_cost_eur=_round(
            machine_cost_eur * params.runs_per_month, 2
        ),
        monthly_net_saving_eur=_round(net_saving * params.runs_per_month, 2),
    )


def load_human_baseline(path: str | Path) -> HumanBaseline:
    """Load a timed baseline, or return the default assumptions.

    A missing file is not an error: it is the normal state as long as
    nobody has timed themselves. The embedded ``measured=False`` in the
    result is enough to signal that the figures are assumptions; no need
    for a noisy degraded mode.
    """
    file = Path(path)
    if not file.exists():
        return HumanBaseline()
    return HumanBaseline.model_validate_json(file.read_text(encoding="utf-8"))


def write_human_baseline(baseline: HumanBaseline, out: str | Path) -> None:
    Path(out).write_text(
        json.dumps(baseline.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
