import os
import sys
from collections.abc import Callable, Mapping

from composition import build_radar_pipeline
from radar.pipeline import PipelineReport, write_report_json
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
DEFAULT_REPORT_PATH = "run_report.json"

Builder = Callable[[Settings], Callable[[], PipelineReport]]


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
    Codes de sortie : 0 = succès ; 2 = configuration manquante (message stderr).
    """
    if env is None:
        env = os.environ
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    report = build(settings)()
    write_report_json(report, out)
    print(
        f"Rapport écrit dans {out} ({report.n_drafted} brouillon(s), "
        f"{report.n_above_threshold} au-dessus du seuil)."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
