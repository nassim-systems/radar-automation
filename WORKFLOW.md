# Workflow — arbitrage d'architecture & orchestration (module 4.1)

## 1. Grille d'arbitrage : flux déterministe / orchestration / agents

Trois façons d'enchaîner des étapes, avec un critère de choix unique : **la
séquence des étapes est-elle connue à l'avance, ou décidée dynamiquement par
un modèle en fonction du contenu ?**

| | Séquence | Qui décide « étape suivante » | Coût/latence | Auditabilité |
|---|---|---|---|---|
| **Flux déterministe** (fonction, ex. `run_pipeline` actuel) | Fixe, en dur dans le code | Personne — c'est le code | Minimal | Le code EST la trace ; rien d'observable à l'exécution sans instrumenter à la main |
| **Orchestration explicite** (`Step` / `run_workflow`, ce module) | Fixe, mais réifiée en objets | Personne — toujours codée, juste composée | Minimal (même travail, juste structuré) | Trace par étape *gratuite* : nom, durée, succès/échec, usage |
| **Agents** (LLM choisit l'action suivante, ex. boucle ReAct) | Dynamique, dépend du contenu | Le modèle, à chaque tour | Élevé (appels LLM pour DÉCIDER, pas seulement pour EXÉCUTER) | Faible par défaut — il faut journaliser chaque décision pour la reconstituer |

**Verdict pour le radar** : le pipeline (fetch → dedup → fresh → unseen →
score → filtre → top-k → draft) a une séquence **strictement fixe**, quel
que soit le contenu des articles. Rien, dans ce pipeline, ne justifie qu'un
LLM décide « et maintenant, quelle étape ? » — cette question a une réponse
statique. Un agent y ajouterait de la latence, du coût et du
non-déterminisme pour zéro bénéfice : **l'orchestration explicite est le bon
niveau**, ni un flux figé illisible-à-l'observation, ni une complexité
d'agent que rien ne justifie.

Ce même critère s'applique à `handle_message` (module 2.5) : son
enchaînement (`classify` → charge conversation → route les outils de
lecture → `draft_reply` → propose l'action) est *lui aussi* une séquence
fixe — c'est un **routage structuré en dur** (`_ROUTES` dans
`agent/agent/runner.py`), pas une boucle agentique. Il est donc, par
construction, un candidat à la même réification — non fait dans ce module
(périmètre : un seul workflow réel, cf. §3), mais la généralité de
l'abstraction est vérifiable par inspection : la forme est identique
(séquence fixe, état qui s'enrichit à chaque étape).

## 2. Décisions d'architecture

### 2.1 Typage de `WorkflowState`

**Décision : ni purement « typé par workflow » ni purement « générique » —
un moteur générique, des états concrets typés par sous-classement.**

`core/workflow/models.py::WorkflowState` est une base Pydantic quasi-vide
(`frozen=True` seulement). `core/workflow/engine.py::Step`/`run_workflow`
sont écrits contre cette base — un seul moteur, réutilisable par n'importe
quel workflow. Chaque workflow concret (ex. `radar/workflow.py::
RadarWorkflowState`) définit sa propre sous-classe avec des champs
typés (`items: list[RawItem]`, `scored: list[ScoredItem]`...) — comme
`PipelineReport`, `RunRecord`, `AgentResult` le font déjà partout ailleurs
dans ce projet. Aucun sac générique (`data: dict[str, Any]`) : ce serait la
seule vraie régression par rapport à l'existant, où *tout* état métier est
un modèle Pydantic typé.

**Pourquoi pas la généricité complète (`Step[S]`/`WorkflowRun[S]` avec
`TypeVar`)** : ce projet n'exécute pas mypy (`check.sh` = `ruff + pytest`) —
paramétrer les types avec des `Generic[S]` ajouterait de la machinerie
`typing` que rien, en CI, ne vérifie. À la place, chaque étape concrète
rétrécit explicitement l'état via `_as_radar_state()` (un simple
`isinstance` + `TypeError` message clair) — le coût de sûreté qu'on
sacrifie en abandonnant les génériques statiques est repayé par une erreur
*explicite et immédiate* si une étape reçoit le mauvais état, plutôt qu'un
`AttributeError` confus plus loin. C'est le même choix que le reste du
projet : préférer une erreur claire à l'exécution à une garantie statique
non vérifiée en pratique.

**Coût accepté** : chaque nouveau workflow définit sa propre sous-classe
d'état (verbeux). C'est un compromis délibéré, pas un oubli — cohérent avec
la discipline « pas de duplication, pas de sac générique » déjà en place
partout dans ce projet.

### 2.2 Gestion des erreurs d'étape : abort, pas skip, pas de compensation

**Décision : une étape qui lève interrompt tout le run (`WorkflowError`,
trace partielle + usage attachés). Pas de « skip d'étape ». Pas de
compensation.**

- **Pas de skip d'étape.** Contrairement à un item dans un lot (où
  « sauter » un item défaillant et continuer sur les autres a du sens — cf.
  `run_pipeline`, isolation des échecs LLM item par item), une **étape** de
  workflow est une unité de travail complète dont dépendent toutes les
  suivantes (`score` a besoin de `unseen`, `draft` a besoin de `top_k`...).
  La sauter silencieusement casserait la suite de façon imprévisible — pire
  qu'un abort franc.
- **La résilience fine reste DANS l'étape, pas dans l'orchestrateur.**
  `DraftStep` (radar/workflow.py) isole encore l'échec LLM item par item en
  interne (`try/except` autour de `llm.complete`, exactement comme
  `run_pipeline` le fait déjà) — c'est la même politique qu'avant, à
  l'intérieur de l'étape. `run_workflow`, lui, ne rattrape que ce qui
  *s'échappe* d'une étape : un vrai bug ou une panne non gérée. Cohérent
  avec la règle déjà appliquée partout ailleurs dans ce projet (scoring,
  drafting, fetch RSS) : les échecs *connus et attendus* sont isolés
  localement ; un bug de code se propage.
- **Pas de compensation (saga/rollback).** Aucune étape du workflow radar
  n'a d'effet de bord à annuler au sens saga : les seuls effets de bord
  (`mark_seen`) sont volontairement placés en toute dernière étape, après
  que tout le reste a réussi — s'il échoue, rien à compenser en amont
  (aucune écriture précédente). Ajouter une machinerie de compensation
  maintenant serait de la complexité sans cas d'usage réel (YAGNI) ; à
  reconsidérer si un futur workflow entrelace des étapes avec effets de
  bord.

### 2.3 Observabilité : réutiliser le `UsageSink` de 3.4, pas le réinventer

**Décision : `run_workflow` ne connaît rien aux tokens/coûts — il délègue
entièrement au `ListUsageSink` du module 3.4.**

`WorkflowRun.usage` est peuplé en appelant `sink.total()` une fois le run
terminé (ou au moment de l'échec, pour le `WorkflowError`) ; le sink lui-même
est le même objet que celui injecté dans `AnthropicClient` (module 3.4) —
les étapes qui font des appels LLM (`ScoreStep`, `DraftStep`) le font via un
`LLMClient` déjà instrumenté, exactement comme `composition.py` le câble
pour `run_pipeline`. **Aucun code de comptage de tokens/coût n'existe dans
`core/workflow/`.**

**Ce qui EST nouveau** (et volontairement, car non couvert par 3.4) : la
durée par étape (`StepTrace.duration_seconds`, mesurée avec
`time.monotonic()`). Le sink d'usage LLM n'a jamais eu vocation à mesurer du
temps d'exécution générique — c'est une préoccupation d'orchestration, pas
de facturation LLM. La distinction est volontaire : réutiliser ce qui existe
déjà (coût/tokens), ajouter seulement ce qui manque réellement (timing par
étape) et qui n'a de sens qu'au niveau de l'orchestrateur.

**Déplacement `radar/llm/usage.py` → `core/usage.py`.** Nécessaire pour que
`core/workflow/` (générique, sans dépendance vers `radar` ni `agent`) puisse
réutiliser `LlmUsage`/`ListUsageSink` sans inverser le sens des dépendances
(`core` est la fondation ; `radar`/`agent`/`executor` s'appuient dessus,
jamais l'inverse — cf. `core/sanitize.py`, déjà partagé par les deux). Le
module lui-même n'avait aucune dépendance interne à `radar` (juste
`pydantic`/`typing`) — le déplacement est mécanique, zéro changement de
comportement, tous les appelants mis à jour et testés.

## 3. Cas d'usage réel : le pipeline radar en workflow

[`src/radar/workflow.py`](src/radar/workflow.py) décompose `run_pipeline` en
**9 `Step`** : `fetch`, `deduplicate`, `filter_fresh`, `filter_unseen`,
`score`, `filter_by_min_score`, `select_top_k`, `draft`, `mark_seen`. Chaque
étape **délègue** à la fonction pure que `run_pipeline` utilise déjà
(`deduplicate`, `filter_fresh`, `score_item`, `filter_by_min_score`,
`select_top_k`, `build_draft_prompt`/`parse_draft`) — **zéro logique
dupliquée**. `run_pipeline` n'a pas été touché ni retiré de production
(`composition.py::build_radar_pipeline` continue de l'utiliser tel quel) :
ce module ajoute une seconde voie, il n'en retire aucune.

### Preuve que ce n'est pas une réécriture cosmétique

1. **Équivalence numérique testée**
   (`tests/test_radar_workflow.py::test_radar_workflow_produces_same_drafts_as_run_pipeline`) :
   mêmes items, même `FakeLLM`, même `PipelineConfig` → le workflow et
   `run_pipeline` produisent exactement les mêmes brouillons, scores et
   compteurs. S'ils divergeaient, ce serait un bug — pas une variante
   acceptable.
2. **Traçabilité que `run_pipeline` n'offre pas.** `PipelineReport` n'a que
   des compteurs agrégés (`n_scored`, `n_drafted`...) — aucune idée du temps
   passé dans chaque étage, ni de quelle étape a échoué le cas échéant.
   `WorkflowRun.trace` donne les deux, gratuitement, pour n'importe quel
   workflow construit avec ce moteur (`tests/test_radar_workflow.py::
   test_radar_workflow_trace_has_one_entry_per_step_all_successful`).
   C'est directement ce qui a manqué lors du diagnostic du module 3.5 :
   sans la liste des items par étage, impossible de savoir après coup quel
   run avait produit quoi (cf. `QUALITY.md`, point 4).
3. **Recomposition sans duplication de code**
   (`tests/test_radar_workflow.py::test_radar_workflow_recomposes_a_scoring_only_dry_run`) :
   un dry-run « scoring seul » (sans `draft` ni `mark_seen`, donc sans appel
   LLM de rédaction ni effet de bord sur le seen-store) s'obtient en
   **filtrant la liste de `Step`** — aucune fonction à copier-coller, aucun
   paramètre `dry_run: bool` à enfiler dans `run_pipeline`. C'est
   exactement le genre de variante qu'un flux en dur ne permet pas sans
   l'éditer.
4. **Abort observable, pas une exception nue.** Si `fetch` échoue,
   `run_pipeline` lève une exception brute et perd tout contexte sur ce qui
   avait déjà tourné. `run_workflow` lève `WorkflowError` avec la trace
   partielle et l'usage déjà accumulé attachés
   (`tests/test_radar_workflow.py::test_radar_workflow_aborts_with_partial_trace_when_fetch_fails`).

### Portée délibérément non couverte par ce module

- `composition.py::build_radar_pipeline` n'est **pas** migré vers ce
  workflow — `run_pipeline` reste le chemin de production. La décomposition
  en `Step` étant strictement équivalente (prouvé en §3.1), migrer serait un
  changement à faible risque mais qui n'a pas été demandé ; le laisser en
  l'état évite de toucher un chemin de production déjà calibré (module 3.5)
  sans nécessité.
- `handle_message` n'est pas réécrit en workflow (cf. §1) — hors périmètre
  de ce module (« au moins un workflow réel »), mais la forme s'y prêterait
  de la même façon.

## Tests

- `tests/test_workflow_engine.py` : moteur générique isolé (état factice,
  pas de dépendance radar) — immuabilité, ordre du threading d'état, trace,
  capture d'usage, abort + enrichissement de l'erreur.
- `tests/test_radar_workflow.py` : cas d'usage réel — ordre des 9 étapes,
  équivalence avec `run_pipeline`, idempotence du `mark_seen`, trace
  complète, capture d'usage à travers `score`+`draft`, abort sur échec de
  fetch, recomposition en dry-run.

```bash
uv run ruff check .
uv run pytest -q
```
