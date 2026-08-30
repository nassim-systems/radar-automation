# Chemin de production unique (module 4.5)

## Décision

**Migration** : `composition.py::build_radar_pipeline` câble désormais
`radar/workflow.py::build_radar_steps_production` (fetch → dedup → fresh →
unseen → score concurrent → seuil → top-K → angle → write → mark_seen).
`run_pipeline` (module 1.x, fonction séquentielle monolithique) est
**supprimée** de `radar/pipeline.py`. Pas de troisième option retenue :
un seul chemin de production existe désormais.

## 1. Les deux options, et pourquoi pas la suppression du workflow

Ce module imposait un choix binaire : migrer vers le workflow, ou
supprimer `radar/workflow.py`/`core/workflow/` et garder `run_pipeline`.

**La suppression du workflow aurait aussi supprimé de la valeur déjà
mesurée**, pas juste de la complexité :
- Module 4.1 a prouvé l'équivalence stricte Step/`run_pipeline` et une
  traçabilité par étape que `run_pipeline` ne peut structurellement pas
  offrir (`PipelineReport` n'a que des agrégats).
- Module 4.2 a **mesuré** (pas supposé) que la décomposition AngleAgent +
  WriterAgent corrige un défaut réel du mono-appel — l'angle PME forcé sur
  un article qui n'en offre pas un honnêtement (`ANGLE_AGENT.md`). Garder
  `run_pipeline` en production aurait signifié garder ce défaut connu et
  déjà corrigé ailleurs dans le dépôt, indéfiniment.
- Module 4.3 a livré un scoring concurrent borné, testé (équivalence
  d'ordre sous latences variables, budget, retry) — un gain de latence réel
  sur `max_scored=30`, que `run_pipeline` (strictement séquentiel) ne peut
  pas offrir.
- Module 4.4 a mesuré et **rejeté** le CriticAgent — donc rien à intégrer
  de ce côté, mais la discipline de mesure appliquée aux trois précédents
  est exactement ce qui rend la migration défendable : chaque brique gardée
  l'a été sur preuve, pas par principe.

Supprimer le workflow aurait donc jeté trois briques mesurées et
retenues pour garder la seule qui n'a **jamais** intégré la correction du
module 4.2. C'est l'argument décisif, pas la préférence pour « plus de
code » : la migration capitalise sur des décisions déjà prises et prouvées
individuellement ; la suppression les aurait annulées sans nouvelle preuve
contraire.

## 2. Voie morte supprimée

- `radar/pipeline.py::run_pipeline` — supprimée. Le module conserve
  uniquement ce que le workflow réutilise : `PipelineConfig`,
  `PipelineReport`, `ScoredDraft`, `filter_by_min_score`,
  `write_report_json`.
- `tests/test_pipeline.py` — réduit aux tests des fonctions pures
  survivantes (`filter_by_min_score`, round-trip UTF-8 de
  `write_report_json`). Les propriétés qu'il vérifiait pour le pipeline
  complet (idempotence, budget, isolation des échecs, seuil) sont
  redémontrées pour la composition de production dans
  `tests/test_radar_workflow_production.py`.
- `tests/test_radar_workflow.py::test_radar_workflow_produces_same_drafts_as_run_pipeline`
  — son objet de comparaison n'existe plus ; remplacé par un test à
  valeurs figées (celles que l'équivalence avait validées en 4.1), pour
  garder cette étape de la migration sous garde-fou sans dépendre d'une
  fonction supprimée.

`build_radar_steps` (mono, séquentiel) et `build_radar_steps_decomposed`
(décomposé, séquentiel) **restent** dans `radar/workflow.py`, testées : ce
ne sont pas des voies mortes mais des compositions alternatives qui
démontrent la recomposition (cf. `WORKFLOW.md`) — la distinction est que
`composition.py` n'en câble plus qu'une seule pour la production.

## 3. Recâblage (`composition.py`)

```diff
- from radar.pipeline import PipelineConfig, run_pipeline
+ from radar.concurrent_scoring import ConcurrentScoringConfig
+ from radar.pipeline import PipelineConfig
+ from radar.workflow import (
+     RadarWorkflowState,
+     build_radar_steps_production,
+     radar_workflow_state_to_pipeline_report,
+ )
+ from core.workflow.engine import run_workflow
```

```diff
      def run() -> RunRecord:
          usage_sink.calls.clear()
          config = PipelineConfig(...)
-        report = run_pipeline(
-            fetch_items=fetch_items, seen_store=seen_store, llm=llm, config=config
-        )
+        steps = build_radar_steps_production(
+            fetch_items=fetch_items, seen_store=seen_store, llm=llm,
+            config=config, concurrency_config=concurrency_config,
+            usage_sink=usage_sink,
+        )
+        workflow_run = run_workflow(steps, RadarWorkflowState(), usage_sink=usage_sink)
+        report = radar_workflow_state_to_pipeline_report(workflow_run.final_state)
          record = RunRecord(at=..., report=report, usage=usage_sink.total())
```

`usage_sink` est injecté à la fois dans `AnthropicClient` **et** dans
`build_radar_steps_production`/`run_workflow` : c'est le même objet aux
trois endroits, condition nécessaire pour que le budget dur de
`ConcurrentScoreStep` (module 4.3) fonctionne réellement (cf.
`CONCURRENCY.md`). `app.py` n'a **aucune modification** à faire : `run()`
renvoie toujours un `RunRecord(at, report: PipelineReport, usage: LlmUsage)`
— le contrat consommé par `write_report_json`/`check_alert` est inchangé.

## 4. Durcissement pour la production

Deux ajustements, nécessaires seulement parce que ce chemin devient
l'unique chemin de production (pas de correction de bug, une évolution
de robustesse justifiée par l'enjeu plus élevé) :

- **`AngleStep` isole désormais les échecs par item.** Avant ce module,
  une erreur LLM sur la décision d'angle d'un seul item faisait échouer
  toute l'étape — donc tout le run (`WorkflowError`, cf.
  `core/workflow/engine.py`). Acceptable pour une mesure ponctuelle (4.2),
  pas pour le seul chemin de production : `AngleStep` suit désormais la
  même politique que `ScoreStep`/`WriteStep` (isolation par item,
  `n_failures` incrémenté, l'item reste « à voir »). Testé :
  `tests/test_radar_workflow_production.py::
  test_angle_step_isolates_a_failing_item_instead_of_aborting_the_run`.
- **`n_llm_calls` reconstruit sur tout le workflow.** Chaque étape qui
  appelle un LLM (`ScoreStep`, `ConcurrentScoreStep`, `DraftStep`,
  `AngleStep`, `WriteStep`) incrémente désormais un compteur porté par
  `RadarWorkflowState`, agrégé par `radar_workflow_state_to_pipeline_report`
  dans le même champ `PipelineReport.n_llm_calls` qu'avant. Pour
  `ConcurrentScoreStep`, le compte inclut les retries réels
  (`report.n_attempted + report.n_retries`) — plus fidèle au nombre
  d'appels API réellement émis que l'ancien compteur de `run_pipeline`, qui
  ne connaissait pas les retries (le retry n'existait pas avant 4.3).

## 5. Non-régression vérifiée

- **`PipelineReport`** : schéma inchangé (mêmes champs, mêmes types).
  `radar_workflow_state_to_pipeline_report` en est la seule source de
  vérité pour la production. Testé :
  `test_radar_workflow_state_to_pipeline_report_maps_all_fields`.
- **`min_score = 8`** : inchangé dans `composition.py`
  (`_MIN_SCORE = 8`, toujours calibré selon `QUALITY.md`). Testé
  end-to-end : `test_production_workflow_respects_min_score`.
- **Idempotence** : un item drafté avec succès est marqué vu ; un item
  skippé (budget, seuil, angle absent, échec) reste « à voir ». Testé sur
  deux runs consécutifs :
  `test_production_workflow_is_idempotent_across_two_runs`.
- **`WorkflowRun` complet** : trace des 10 étapes avec durées, usage
  agrégé, brouillons dans l'état final — testé
  (`test_production_workflow_produces_a_complete_workflow_run`) et vérifié
  sur un run réel (§6).
- Suite complète : `uv run pytest -q` → 235 passed. `uv run ruff check .`
  → clean.

## 6. Run réel de vérification

Store vidé, flux réels (Zapier/n8n en plus des flux généralistes existants)
pour observer un vrai drafting de bout en bout à travers la nouvelle
composition :

```
Rapport écrit dans run_report.json (3 brouillon(s), 3 au-dessus du seuil, 0.0214 USD).
```

`run_report.json` (schéma `PipelineReport` inchangé) : `n_fetched=57,
n_scored=30, n_above_threshold=3, n_drafted=3, n_llm_calls=36, n_failures=0`
— cohérent (30 scoring + 3 angle + 3 write = 36). Les 3 brouillons (Claude ×
Zapier, générateurs de sites IA, Claude pour petites entreprises) sont
naturels, aucun angle forcé détecté à la relecture. `.data/run_history.json`
a correctement archivé le `RunRecord` à la suite de l'historique existant
(module 3.4).

## Reproductibilité

```bash
uv run ruff check .
uv run pytest -q
./check.sh
```
