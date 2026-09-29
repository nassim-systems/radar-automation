# radar-automation

*EN — An automated monitoring pipeline (RSS → relevance scoring → draft posts). What is worth reading here is not that it works: every design decision is measured before it is kept, including the decision to remove a component. Decision records are written in French.*

Un système de veille automatisé : il lit des flux RSS, note la pertinence de chaque article pour une PME, et rédige un brouillon de post pour les rares articles qui passent le seuil.

Ce qui est intéressant ici n'est pas qu'il fonctionne. C'est que **chaque décision d'architecture est mesurée avant d'être gardée, y compris celle de retirer un composant.**

## À lire en premier

| Document | Ce qu'il montre |
|---|---|
| [`QUALITY.md`](QUALITY.md) | Comment le seuil de pertinence est calibré : jeu réel annoté à la main, précision et rappel par seuil, limites écrites noir sur blanc. |
| [`CRITIC_AGENT.md`](CRITIC_AGENT.md) | Un agent relecteur construit, testé, mesuré, puis **jeté** : 67 % de faux rejets sur 14 cas réels. |
| [`OBSERVABILITY.md`](OBSERVABILITY.md) | Trace horodatée par étape, par article et par appel LLM ; ce qui est mesuré et ce qui n'est qu'une hypothèse. |

Les autres décisions : [`WORKFLOW.md`](WORKFLOW.md) (pourquoi une orchestration explicite plutôt qu'un agent), [`ANGLE_AGENT.md`](ANGLE_AGENT.md), [`CONCURRENCY.md`](CONCURRENCY.md), [`MIGRATION.md`](MIGRATION.md), [`HELDOUT.md`](HELDOUT.md).

## Le pipeline

```
fetch → deduplicate → filter_fresh → filter_unseen → score → filter_by_min_score
      → select_top_k → angle → write → mark_seen
```

Dix étapes, dont trois appellent un modèle (`score`, `angle`, `write`). Les sept autres sont du code déterministe et testé : la séquence est fixe quel que soit le contenu, aucune raison de faire décider un modèle de l'étape suivante.

## Chiffres vérifiables dans ce dépôt

- **264 tests**, `ruff` propre.
- [`run_trace.json`](run_trace.json), un run réel du 1ᵉʳ septembre 2026 : 17 articles notés, 17 appels au modèle, 0 échec, **3,8 s** de bout en bout pour 13,4 s d'appels cumulés (gain de parallélisme ×4,0), coût 0,008 $.
- [`docs/run_history.json`](docs/run_history.json), trois runs réels : 73 appels, 0 échec, ≈ 0,040 $ au total.

## Limites, assumées

- **Rappel de 70 %** au seuil retenu : 3 articles pertinents sur 10 ne sont pas traités ce jour-là. Choix documenté dans `QUALITY.md` : rater un article coûte moins cher que publier un mauvais brouillon.
- **Échantillons petits** (n = 10 à 30 selon la mesure) : les tendances sont nettes, les intervalles de confiance larges.
- **Le système produit peu** : deux des trois runs enregistrés n'ont donné aucun brouillon. C'est un filtre exigeant, pas une machine à contenu.

## Lancer et reproduire

```bash
uv run ruff check . && uv run pytest -q     # 264 tests

export ANTHROPIC_API_KEY=...                # jamais dans le code ni dans git
export FEED_URLS=https://exemple.com/feed,https://autre.com/rss
uv run radar-run                            # écrit run_report.json et run_trace.json
```

L'ordonnancement quotidien (cron, Planificateur de tâches) est décrit dans [`docs/ordonnancement.md`](docs/ordonnancement.md).

## À propos de la numérotation

Dans les documents et les commentaires, un « module 4.5 » désigne une **étape du projet numérotée dans l'ordre où elle a été réalisée** (1.x à 3.x : pipeline, agent, observabilité, calibration ; 4.x : arbitrages d'architecture). Les arbitrages 4.x et la calibration ont chacun leur document, qui donne la question posée, la mesure et la décision.

## Stack

Python ≥ 3.11 · Pydantic · SDK Anthropic (Claude Haiku 4.5) · pytest · ruff.
