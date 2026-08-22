import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from composition import build_radar_pipeline
from radar.pipeline import PipelineReport
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
DEFAULT_REPORT_PATH = "run_report.json"

Builder = Callable[[Settings], Callable[[], PipelineReport]]


def main(
    env: Mapping[str, str],
    *,
    build: Builder = build_radar_pipeline,
    out: str = DEFAULT_REPORT_PATH,
) -> int:
    """Charge la config, câble et exécute le pipeline radar, écrit le rapport.

    Écrit ``out`` en UTF-8 explicite (indépendant de toute redirection shell).
    Codes de sortie : 0 = succès ; 2 = configuration manquante (message stderr).
    """
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    report = build(settings)()
    Path(out).write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Rapport écrit dans {out} ({report.n_drafted} brouillon(s)).")
    return EXIT_OK


def run() -> int:
    """Point d'entrée console (commande ``run-radar``)."""
    return main(os.environ)


if __name__ == "__main__":
    sys.exit(run())
