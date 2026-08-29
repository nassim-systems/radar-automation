# Ordonnancement du radar

## Principe : pas d'ordonnanceur maison

`scripts/run_radar.py` est un **one-shot** : il exécute un run puis se termine.
La périodicité est déléguée à l'ordonnanceur de l'OS. Réimplémenter un
scheduler (boucle, `while True: sleep`, gestion de dérive, persistance des
prochains déclenchements…) serait redondant, fragile et non testé — cron et
Task Scheduler font déjà ce travail de façon robuste et supervisée.

## Linux / macOS — cron

Exemple : tous les jours à 08:00, avec logs.

```cron
0 8 * * * cd /opt/radar && uv run python scripts/run_radar.py >> /var/log/radar.log 2>&1
```

Les secrets viennent de l'environnement du service (ou d'un `.env` chargé par un
wrapper) — **jamais** en clair dans une crontab partagée.

## Windows — Task Scheduler

```bat
schtasks /Create /SC DAILY /ST 08:00 /TN "RadarRun" ^
  /TR "cmd /c cd /d C:\radar && uv run python scripts\run_radar.py >> logs\radar.log 2>&1"
```

Les variables (`ANTHROPIC_API_KEY`, `FEED_URLS`, `STORE_DIR`) sont définies au
niveau **Utilisateur** ou **Système**, hors du dépôt.

## Gestion d'erreur réseau : skip + continue (décision)

Sur échec de récupération d'un flux (réseau, HTTP, XML malformé), on **skippe ce
flux et on continue** avec les autres, plutôt que d'**abort** tout le run. Un
radar est multi-sources : un flux mort ou lent ne doit pas annuler la collecte
des autres. La décision est implémentée dans le fetcher de la racine de
composition (`_make_feed_fetcher`, `except (OSError, ParseError): continue`).

Les **bugs de code** (hors I/O réseau/parsing), eux, remontent volontairement.

## Codes de sortie

| Code | Signification |
|---|---|
| `0` | Succès — `PipelineReport` écrit dans le fichier de rapport (JSON, UTF-8). |
| `2` | Configuration manquante (ex. `ANTHROPIC_API_KEY`) — message clair sur stderr. |
| `3` | Alerte (module 3.4) — coût du run ou échecs LLM au-dessus du seuil — message sur stderr. Le rapport est quand même écrit. |
| autre / traceback | Erreur non gérée — visible dans les logs, l'ordonnanceur peut alerter. |

L'ordonnanceur (cron/Task Scheduler) peut se baser sur ce code de sortie pour
notifier ou relancer.
