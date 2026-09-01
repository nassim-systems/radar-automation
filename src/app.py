import os
import sys
from collections.abc import Callable, Mapping

from composition import build_radar_pipeline
from radar.observability.alert import check_alert
from radar.observability.trace import RadarRunOutcome, write_trace_json
from radar.observability.value import compute_value_equation, load_human_baseline
from radar.pipeline import write_report_json
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_ALERT = 3
DEFAULT_REPORT_PATH = "run_report.json"
DEFAULT_TRACE_PATH = "run_trace.json"
DEFAULT_BASELINE_PATH = "human_baseline.json"
MAX_COST_USD_ALERT = 1.0  # seuil d'alerte coût/run (module 3.4)

Builder = Callable[[Settings], Callable[[], RadarRunOutcome]]


def main(  # noqa: PLR0913
    env: Mapping[str, str] | None = None,
    *,
    build: Builder = build_radar_pipeline,
    out: str = DEFAULT_REPORT_PATH,
    trace_out: str = DEFAULT_TRACE_PATH,
    baseline_path: str = DEFAULT_BASELINE_PATH,
) -> int:
    """Charge la config, câble et exécute le pipeline radar, écrit le rapport.

    Point d'entrée console (commande ``radar-run``) : ``env`` par défaut sur
    ``os.environ`` pour être appelable sans argument. Écrit ``out`` en UTF-8
    explicite (indépendant de toute redirection shell).

    Codes de sortie : 0 = succès ; 2 = configuration manquante (stderr) ;
    3 = alerte (coût du run ou échecs LLM au-dessus du seuil — stderr). Le
    rapport est écrit avant la vérification d'alerte : une alerte n'empêche
    pas d'avoir le rapport sous la main.

    **Deux artefacts, deux responsabilités** (module 4.6, ``OBSERVABILITY.md``)
    : ``out`` reçoit le ``PipelineReport`` au schéma inchangé, ``trace_out``
    la trace détaillée du même run. L'équation de valeur est appliquée ici,
    et pas dans la composition, parce qu'elle repose sur des **hypothèses
    commerciales** (``baseline_path``) et non sur la mesure : le runner
    mesure, le point d'entrée interprète. Sans fichier de baseline, les
    hypothèses par défaut sont utilisées et signalées comme telles
    (``value.baseline.measured = false``).
    """
    if env is None:
        env = os.environ
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    outcome = build(settings)()
    record = outcome.record
    write_report_json(record.report, out)
    trace = outcome.trace.model_copy(
        update={
            "value": compute_value_equation(
                report=record.report,
                machine_seconds=outcome.trace.latency.run_seconds,
                machine_cost_usd=record.usage.cost_usd,
                baseline=load_human_baseline(baseline_path),
            )
        }
    )
    write_trace_json(trace, trace_out)
    print(
        f"Rapport écrit dans {out} ({record.report.n_drafted} brouillon(s), "
        f"{record.report.n_above_threshold} au-dessus du seuil, "
        f"{record.usage.cost_usd:.4f} USD, "
        f"{trace.latency.run_seconds:.1f} s)."
    )
    print(
        f"Trace écrite dans {trace_out} "
        f"({trace.n_llm_calls_traced} appel(s) LLM, "
        f"{trace.latency.llm_cumulative_seconds:.1f} s cumulées)."
    )
    alert = check_alert(record, max_cost_usd=MAX_COST_USD_ALERT)
    if alert is not None:
        print(f"ALERTE : {alert}", file=sys.stderr)
        return EXIT_ALERT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
