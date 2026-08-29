import os
import sys
from collections.abc import Callable, Mapping

from composition import build_radar_pipeline
from radar.observability.alert import check_alert
from radar.observability.models import RunRecord
from radar.pipeline import write_report_json
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_ALERT = 3
DEFAULT_REPORT_PATH = "run_report.json"
MAX_COST_USD_ALERT = 1.0  # seuil d'alerte coût/run (module 3.4)

Builder = Callable[[Settings], Callable[[], RunRecord]]


def main(
    env: Mapping[str, str] | None = None,
    *,
    build: Builder = build_radar_pipeline,
    out: str = DEFAULT_REPORT_PATH,
) -> int:
    """Charge la config, câble et exécute le pipeline radar, écrit le rapport.

    Point d'entrée console (commande ``radar-run``) : ``env`` par défaut sur
    ``os.environ`` pour être appelable sans argument. Écrit ``out`` en UTF-8
    explicite (indépendant de toute redirection shell).

    Codes de sortie : 0 = succès ; 2 = configuration manquante (stderr) ;
    3 = alerte (coût du run ou échecs LLM au-dessus du seuil — stderr). Le
    rapport est écrit avant la vérification d'alerte : une alerte n'empêche
    pas d'avoir le rapport sous la main.
    """
    if env is None:
        env = os.environ
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    record = build(settings)()
    write_report_json(record.report, out)
    print(
        f"Rapport écrit dans {out} ({record.report.n_drafted} brouillon(s), "
        f"{record.report.n_above_threshold} au-dessus du seuil, "
        f"{record.usage.cost_usd:.4f} USD)."
    )
    alert = check_alert(record, max_cost_usd=MAX_COST_USD_ALERT)
    if alert is not None:
        print(f"ALERTE : {alert}", file=sys.stderr)
        return EXIT_ALERT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
