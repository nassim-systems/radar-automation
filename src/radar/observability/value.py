"""Équation de valeur humaine (module 4.6) : temps humain remplacé, coût
équivalent, projection de ROI.

**Statut épistémique de ce module — à lire avant d'utiliser ses chiffres.**
Tout ce qui précède dans ce projet est *mesuré* : les scores viennent d'un
held-out annoté, les coûts du SDK, les latences d'une horloge. Ici, non. Une
équation de valeur repose sur des **paramètres humains** (combien de temps
met une personne à trier un article, à rédiger un post, combien coûte son
heure) que ce dépôt ne peut pas mesurer tout seul.

La séparation est donc explicite et matérialisée dans le type :
``HumanBaseline`` porte les *hypothèses*, ``ValueEquation`` porte le *calcul*,
et ``HumanBaseline.measured`` dit si les paramètres viennent d'un
chronométrage réel (``scripts/measure_human_baseline.py``) ou des valeurs par
défaut ci-dessous. Un chiffre de ROI dont ``measured`` vaut ``False`` est une
projection paramétrique, pas un résultat — et il doit être présenté comme tel.

Les valeurs par défaut ne sont pas des mesures déguisées : ce sont des
ordres de grandeur prudents, choisis pour être remplacés.
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
    """Paramètres du travail humain que le radar remplace ou allège.

    ``seconds_per_draft_review`` est le point d'honnêteté de ce modèle : le
    système ne supprime pas le travail humain, il le déplace. Un brouillon
    produit doit encore être relu et validé — ce temps résiduel est déduit du
    gain, jamais ignoré. Sans ce terme, l'équation surestimerait le gain de
    façon systématique.
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
    """Résultat du calcul, avec ses hypothèses attachées.

    ``baseline`` est embarquée volontairement : un chiffre de ROI séparé de
    ses paramètres est ininterprétable, et pire, réutilisable hors contexte.
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
    """Applique ``baseline`` aux compteurs réels d'un run.

    Le volume de travail humain remplacé est indexé sur ce que le système a
    *réellement* fait ce run-là (``n_scored`` items triés, ``n_drafted``
    brouillons rédigés) — pas sur une capacité théorique. Un run qui ne
    drafte rien produit donc un gain de rédaction nul, ce qui est le
    comportement voulu : l'équation suit la production réelle, y compris
    quand elle est basse.

    ``roi_ratio`` et ``time_compression_ratio`` valent ``None`` plutôt que
    l'infini quand leur dénominateur est nul — un ratio non calculable ne
    doit pas se présenter comme un très grand nombre.
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
    """Charge une baseline chronométrée, ou renvoie les hypothèses par défaut.

    L'absence de fichier n'est pas une erreur : c'est l'état normal tant que
    personne ne s'est chronométré. Le ``measured=False`` embarqué dans le
    résultat suffit à signaler que les chiffres sont des hypothèses — pas
    besoin d'un mode dégradé bruyant.
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
