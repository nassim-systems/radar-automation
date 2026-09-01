"""Chronomètre le travail humain que le radar remplace (module 4.6).

Transforme les hypothèses par défaut de ``radar/observability/value.py`` en
**mesure**. Le protocole est volontairement rudimentaire — un chronomètre et
une personne — mais il a la propriété qui compte : les items triés sont ceux
d'un run réel (lus depuis ``run_trace.json``), pas des exemples choisis pour
l'exercice.

Ce que ce script ne fait pas : il ne mesure qu'**un** annotateur, une fois.
C'est la même limite de non-indépendance que partout ailleurs dans ce projet
(cf. ``QUALITY.md``, ``ANGLE_AGENT.md``) — assumée, pas masquée. Le résultat
reste infiniment préférable à un chiffre inventé, et il est marqué
``measured=true`` pour qu'on ne le confonde jamais avec une hypothèse —
**uniquement si l'opérateur confirme explicitement** avoir chronométré pour
de vrai (``_is_measured_confirmed``) ; toute autre réponse force
``measured=false``, jamais l'inverse par défaut.

Usage :

    uv run python scripts/measure_human_baseline.py [run_trace.json]
"""
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar.observability.trace import RunTrace  # noqa: E402
from radar.observability.value import (  # noqa: E402
    HumanBaseline,
    write_human_baseline,
)

DEFAULT_TRACE = REPO / "run_trace.json"
DEFAULT_OUT = REPO / "human_baseline.json"
MAX_ITEMS = 12
DEFAULT_HOURLY_COST_EUR = 50.0
DEFAULT_RUNS_PER_MONTH = 21
DEFAULT_EUR_PER_USD = 0.92


def _chrono(label: str) -> float:
    """Mesure le temps entre deux Entrée. ``time.monotonic`` : insensible à
    un ajustement d'horloge pendant la mesure."""
    input(f"{label}\n  → Entrée pour DÉMARRER…")
    started = time.monotonic()
    input("  → Entrée quand c'est FAIT…")
    elapsed = time.monotonic() - started
    print(f"  ⏱  {elapsed:.1f} s\n")
    return elapsed


def _is_measured_confirmed(response: str) -> bool:
    """``True`` seulement si l'opérateur a répondu exactement « oui »
    (insensible à la casse et aux espaces superflus) — toute autre réponse,
    y compris une entrée vide (Entrée pressée sans réfléchir), force
    ``measured=False``. Fonction pure, testable sans mock d'``input``.
    """
    return response.strip().lower() == "oui"


def _ask_float(label: str, default: float) -> float:
    raw = input(f"{label} [{default}] : ").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        print(f"  valeur illisible, on garde {default}")
        return default


def _measure_triage(trace: RunTrace) -> float | None:
    """Chronomètre le tri d'items **réels** du dernier run."""
    items = trace.items[:MAX_ITEMS]
    if not items:
        print("Aucun item dans la trace : impossible de chronométrer le tri.")
        return None

    print(
        f"\n=== 1/3 — Tri ({len(items)} items réels du run du "
        f"{trace.run_at:%Y-%m-%d}) ===\n"
        "Pour chaque item : lisez le titre (ouvrez l'URL si vous le feriez "
        "vraiment), décidez s'il mérite un post, puis validez.\n"
    )
    durations: list[float] = []
    for position, item in enumerate(items, start=1):
        print(f"[{position}/{len(items)}] {item.subject.title}")
        if item.subject.url:
            print(f"          {item.subject.url}")
        durations.append(_chrono("  Trier cet item"))
    mean = sum(durations) / len(durations)
    print(f"→ Tri : {mean:.1f} s/item en moyenne (n={len(durations)})\n")
    return mean


def main() -> int:
    trace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE
    if not trace_path.exists():
        print(
            f"Trace introuvable : {trace_path}\n"
            "Lancez d'abord un run (`uv run radar-run`) — le chronométrage "
            "porte sur les items réels de ce run, pas sur des exemples.",
            file=sys.stderr,
        )
        return 2

    trace = RunTrace.model_validate_json(trace_path.read_text(encoding="utf-8"))
    triage = _measure_triage(trace)
    if triage is None:
        return 2

    print("=== 2/3 — Rédaction ===")
    print("Rédigez un post complet à partir d'un de ces articles, comme vous")
    print("le publieriez vraiment.\n")
    drafting = _chrono("  Rédiger un post de bout en bout")

    print("=== 3/3 — Relecture ===")
    print("Relisez un brouillon produit par le radar (run_report.json) et")
    print("décidez de le publier, corriger ou jeter.\n")
    review = _chrono("  Relire et valider un brouillon")

    print("=== Paramètres économiques ===")
    hourly = _ask_float("Coût horaire chargé (EUR/h)", DEFAULT_HOURLY_COST_EUR)
    runs = _ask_float("Runs par mois", float(DEFAULT_RUNS_PER_MONTH))
    rate = _ask_float("Taux EUR par USD", DEFAULT_EUR_PER_USD)

    print("=== Confirmation ===")
    response = input("Avez-vous chronométré réellement ? (oui/non) : ")
    measured = _is_measured_confirmed(response)
    if measured:
        note = (
            f"Chronométré sur {len(trace.items[:MAX_ITEMS])} items réels du run "
            f"du {trace.run_at:%Y-%m-%d} ; un seul annotateur, une seule passe "
            "(même limite de non-indépendance que QUALITY.md)."
        )
    else:
        print(
            "  Réponse différente de « oui » : measured est forcé à false. "
            "Les hypothèses par défaut resteront utilisées tant qu'un "
            "chronométrage confirmé n'aura pas été fait."
        )
        note = (
            "measured=false : la confirmation opérateur n'a pas répondu "
            "exactement « oui » — les temps ci-dessus ne doivent pas être "
            "traités comme un chronométrage réel."
        )

    baseline = HumanBaseline(
        seconds_per_item_triage=round(triage, 1),
        seconds_per_draft=round(drafting, 1),
        seconds_per_draft_review=round(review, 1),
        hourly_cost_eur=hourly,
        runs_per_month=int(runs),
        eur_per_usd=rate,
        measured=measured,
        measured_at=datetime.now(tz=UTC),
        note=note,
    )
    write_human_baseline(baseline, DEFAULT_OUT)
    print(f"\nBaseline écrite dans {DEFAULT_OUT} (measured={measured}).")
    if measured:
        print(
            "Le prochain run l'utilisera automatiquement "
            "(value.baseline.measured = true)."
        )
    else:
        print("Le prochain run continuera d'utiliser les hypothèses par défaut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
