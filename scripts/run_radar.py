"""Point d'entrée du radar.

Flux : ``load_settings(os.environ)`` → ``build_radar_pipeline`` → ``run()`` →
sérialisation du ``PipelineReport`` en JSON sur stdout.

Ordonnancement : ce script est un one-shot déclenché par l'ordonnanceur de l'OS
(cron / Task Scheduler) — voir ``docs/ordonnancement.md``. Aucun ordonnanceur
maison ici.

Codes de sortie : 0 = succès ; 2 = configuration manquante (message sur stderr).
Toute autre erreur non gérée remonte (exit non-zéro + traceback dans les logs).
"""
import json
import os
import sys
from collections.abc import Callable, Mapping

from composition import build_radar_pipeline
from radar.pipeline import PipelineReport
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2

Builder = Callable[[Settings], Callable[[], PipelineReport]]


def main(env: Mapping[str, str], *, build: Builder = build_radar_pipeline) -> int:
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    report = build(settings)()
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(os.environ))
