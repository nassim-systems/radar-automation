# Trace, latences et valeur humaine (module 4.6)

## Décision

**Gardé, avec une frontière nette entre ce qui est mesuré et ce qui est
supposé.** Trois briques livrées :

1. **Trace horodatée exportable** — chaque étape, chaque item et chaque appel
   LLM d'un run, dans `run_trace.json`.
2. **Latences** — par appel, par item, par phase, par étape, et de bout en
   bout, avec le gain de concurrence mesuré plutôt qu'affirmé.
3. **Équation de valeur humaine** — temps humain remplacé, coût équivalent,
   projection de ROI, **explicitement paramétrique** tant qu'un chronométrage
   réel n'a pas eu lieu.

La troisième n'est pas de même nature que les deux premières, et le code le
dit : `HumanBaseline.measured` distingue une hypothèse d'une mesure. C'est la
décision structurante de ce module.

## 1. Contexte

Les modules 4.1 à 4.5 ont produit de l'observabilité réelle — durée par étape
(`WorkflowRun.trace`), tokens et coût (`UsageSink`) — mais **rien n'en
sortait du processus**. `run_report.json` ne contient que des compteurs
agrégés ; c'est exactement le manque diagnostiqué au module 3.5
(`QUALITY.md` §4 : « le batch exact du run n'a pas été conservé… impossible
de le reconstituer a posteriori »). L'auditabilité était une propriété du
moteur, pas un artefact consultable.

Deuxième manque, plus embarrassant : **aucune latence nulle part**. Le projet
mesure sa précision et son coût au millième de dollar, et ne sait pas dire
combien de temps un run prend.

Troisième manque, d'une autre nature : le coût d'un run (0,0214 USD) est un
chiffre orphelin. Pas cher **comparé à quoi** ? Sans terme de comparaison
humain, il ne démontre rien.

## 2. Décisions d'architecture

### 2.1 Un artefact séparé, pas un `PipelineReport` élargi

**Décision : `run_trace.json`, apparié à `run_report.json` par `run_at`.**

`MIGRATION.md` §5 pose une non-régression explicite — le schéma de
`PipelineReport` est inchangé — et c'est elle qui a rendu la migration du
module 4.5 vérifiable. `RunRecord` (donc `run_history.json`, deux runs déjà
archivés) en dépend directement. Y greffer la trace romprait cette garantie
pour une raison purement cosmétique.

Coût accepté : deux fichiers à lire au lieu d'un. En échange, un contrat de
plus, aucun contrat cassé, et un `run_trace.json` que rien n'oblige à
produire — un appelant qui ne veut que le rapport ne paie rien.

Les brouillons ne sont **pas** dupliqués dans la trace : ils vivent dans
`run_report.json`. Deux copies à garder cohérentes pour zéro information
nouvelle, c'est le genre de duplication que ce projet refuse ailleurs.

### 2.2 Un décorateur `LLMClient`, pas un `AnthropicClient` modifié

**Décision : `TimedLLMClient` décore n'importe quel `LLMClient`.**

Même raisonnement que pour le `UsageSink` du module 3.4 : le client réel n'a
pas à connaître l'observabilité. Conséquence utile : les `FakeLLM` /
`ScriptedFakeLLM` des tests sont instrumentables exactement comme le client
de production — l'intégralité des tests de trace tourne sans clé API.

**Attribution explicite, pas devinée.** Le décorateur porte le *sujet* de
l'appel (l'item) et sa *phase* (le nom de l'étape) : chaque étape crée un
décorateur par item. Rien n'est reconstitué après coup par corrélation
temporelle, ce qui serait faux dès qu'il y a de la concurrence.

**Le nom de phase est le nom de l'étape, par construction.** C'est ce qui
permet de rapprocher le temps *cumulé* des appels d'une phase du temps *réel*
de l'étape correspondante — et donc de mesurer le gain de concurrence
(§3.2) au lieu de l'affirmer.

### 2.3 Attribution de l'usage : thread-local assumé

**Décision : `CallTimeline` implémente `UsageSink` et attribue l'usage reçu à
l'appel en cours dans le thread courant, via `TeeUsageSink`.**

C'est le seul point délicat du module, donc le plus testé. La correction
tient à une propriété précise : `AnthropicClient.complete` notifie son sink
de façon **synchrone, dans le thread qui exécute l'appel** — le même que
celui du décorateur, y compris dans le `ThreadPoolExecutor` du scoring
concurrent (module 4.3). Un test dédié le vérifie avec six appels parallèles
aux coûts distincts et aux latences volontairement inversées : si
l'attribution passait par un état partagé, les coûts se mélangeraient
(`tests/test_llm_timing.py::test_attribution_stays_correct_across_concurrent_calls`).

**Aucun comptage réinventé** : la source reste l'usage renvoyé par le SDK.
`TeeUsageSink` diffuse le même objet au `ListUsageSink` (budget dur, total du
`RunRecord`) et à la timeline (attribution par appel) — deux consommateurs,
une source, pas deux comptages susceptibles de diverger.

**Défaut sûr** : un usage reçu hors de tout appel instrumenté est **ignoré**,
pas attribué au hasard. Un champ absent vaut mieux qu'un chiffre faux — même
asymétrie que le fail-closed du `CriticAgent` (`CRITIC_AGENT.md` §2).

### 2.4 Instrumentation strictement optionnelle

`timeline=None` partout par défaut. Aucune étape ne prend un chemin de code
différent selon qu'elle est instrumentée ou non : le décorateur est appliqué
ou l'identité l'est. **Preuve** : les 235 tests d'avant ce module passent
sans modification après l'ajout de l'instrumentation. Les seuls tests
retouchés (`test_entrypoint.py`) le sont parce que le runner renvoie
désormais deux objets — pas parce qu'un comportement a changé.

### 2.5 Le runner mesure, le point d'entrée interprète

**Décision : l'équation de valeur est appliquée dans `app.py`, pas dans
`composition.py`.**

La trace est une mesure ; l'équation repose sur des **hypothèses
commerciales** (coût horaire, temps de tri, runs par mois). Les mélanger dans
le même étage rendrait impossible de dire lequel des deux chiffres est
observé. `composition.py` produit donc une trace sans équation, et `app.py`
lui applique la baseline chargée depuis `human_baseline.json` — absent par
défaut, auquel cas les hypothèses par défaut sont utilisées **et signalées**
(`value.baseline.measured = false`).

## 3. Ce que la trace donne réellement

### 3.1 Deux compteurs indépendants qui doivent coïncider

`counters.n_llm_calls` est reconstruit par les étapes (module 4.5, retries
inclus) ; `n_llm_calls_traced` est le nombre d'enregistrements réellement
produits par les appels. Les deux sont obtenus par des chemins **distincts** —
c'est précisément ce qui permet de voir un écart s'il apparaît. Un run où ils
divergent est un bug, pas une variante acceptable.

### 3.2 Le gain de concurrence, mesuré

`PhaseTiming.speedup` = temps cumulé des appels d'une phase ÷ temps réel de
l'étape homonyme. À 1,0 l'étape est séquentielle ; au-dessus, elle recouvre
ses appels. Sur une exécution de démonstration à 6 items et 5 appels
concurrents (LLM factice à latence fixe, `max_concurrency=5`) :

| Phase | Appels | Cumulé | Réel (étape) | Speedup |
|---|---|---|---|---|
| `score` | 6 | 0,901 s | 0,302 s | **2,98** |
| `angle` | 3 | 0,451 s | 0,451 s | 1,00 |
| `write` | 3 | 0,451 s | 0,451 s | 1,00 |

C'est la première vérification **de bout en bout** de la promesse du module
4.3 : le scoring recouvre bien ses appels, l'angle et la rédaction restent
séquentiels — ce qui est le comportement voulu, pas un défaut.

> **Ces chiffres viennent d'un LLM factice**, pas d'un run réel : ils
> valident la mécanique de mesure, pas la latence de production. Le premier
> run réel avec `run_trace.json` remplacera ce tableau.

### 3.3 Le coût d'orchestration, gardé visible

`latency.orchestration_seconds` est l'écart entre la durée réelle du run et
la somme des étapes. Le garder explicite évite la tentation, courante, de
présenter la somme des étapes comme la durée du run. Sur la démonstration
ci-dessus : 0,1 ms sur 1,2 s — le moteur ne coûte rien, mais c'est désormais
une mesure, pas une intuition.

## 4. L'équation de valeur — portée et honnêteté

Tout le reste de ce projet est mesuré : les scores viennent d'un held-out
annoté, les coûts du SDK, les latences d'une horloge. **Ici, non.** Une
équation de valeur repose sur des paramètres humains que ce dépôt ne peut pas
mesurer seul.

La séparation est matérialisée dans le type : `HumanBaseline` porte les
hypothèses, `ValueEquation` porte le calcul, et `ValueEquation.baseline`
embarque les paramètres avec le résultat — un chiffre de ROI séparé de ses
hypothèses est ininterprétable, et pire, réutilisable hors contexte.

**Le terme qui empêche la surestimation.** `seconds_per_draft_review` : le
système ne supprime pas le travail humain, il le déplace. Un brouillon
produit doit encore être relu et validé, et ce temps résiduel est **déduit**
du gain. Sans ce terme, l'équation surestimerait systématiquement — c'est
l'erreur standard de tous les calculateurs de ROI d'automatisation, et elle
est ici évitée par construction, pas par vigilance.

**Ratios non calculables.** `roi_ratio` et `time_compression_ratio` valent
`None` plutôt que l'infini quand leur dénominateur est nul. Un ratio
indéfini ne doit pas se présenter comme un très grand nombre.

**L'équation suit la production réelle**, pas une capacité théorique : un run
qui ne drafte rien produit un gain de rédaction nul. Les runs réels de 3.3,
3.4 et 3.5 ayant tous drafté 0 item, ce cas n'est pas hypothétique.

**Ce que cette équation ne prouvera jamais**, même chronométrée : que le
travail humain remplacé avait de la valeur. Elle chiffre un temps évité, pas
un bénéfice obtenu. La distinction doit rester explicite partout où ces
chiffres sont présentés.

### Passer de l'hypothèse à la mesure

`scripts/measure_human_baseline.py` chronomètre le tri sur les **items réels
du dernier run** (lus depuis `run_trace.json`, pas des exemples choisis pour
l'exercice), puis la rédaction et la relecture, et écrit
`human_baseline.json` avec `measured=true`. Limite assumée, identique à celle
de `QUALITY.md` et `ANGLE_AGENT.md` : un seul annotateur, une seule passe.

## 5. Portée (honnête)

- **Aucun run réel n'a encore produit de `run_trace.json`.** La mécanique est
  testée de bout en bout avec des LLM factices ; les latences de production
  restent inconnues jusqu'au prochain run avec clé API.
- **Les latences mesurées incluent le réseau et le service**, sans les
  distinguer : `duration_seconds` est le temps vu par l'appelant, pas le
  temps de calcul du modèle. C'est la bonne mesure pour dimensionner un run,
  pas pour diagnostiquer une lenteur côté fournisseur.
- **Le budget par défaut de `HumanBaseline` n'est pas une mesure déguisée**
  (25 s de tri, 8 min de rédaction, 45 s de relecture, 50 €/h) : ce sont des
  ordres de grandeur choisis pour être remplacés.
- **`speedup` compare une phase à une étape homonyme.** Une phase sans étape
  correspondante ne reporte pas de speedup plutôt qu'un ratio inventé.

## 6. Tests

- `tests/test_llm_timing.py` (6) : transparence du décorateur, appel en
  échec tracé et exception propagée, attribution de l'usage, usage hors appel
  ignoré, **attribution correcte sous concurrence**, réinitialisation.
- `tests/test_run_trace.py` (8) : speedup, absence de speedup sans étape,
  agrégation par item, appels sans sujet exclus, run de production complet
  (phases, items, coïncidence des deux compteurs), latences et horodatages,
  round-trip UTF-8, run vide sans ratio inventé.
- `tests/test_value_equation.py` (8) : arithmétique, déduction de la
  relecture, projection mensuelle, run sans brouillon, ratios `None`,
  baseline par défaut annoncée non mesurée, round-trip disque.
- `tests/test_workflow_engine.py` (+) : horodatage des étapes, ordre,
  durée du run ≥ somme des étapes, étape en échec horodatée.
- `tests/test_entrypoint.py` (+) : deux artefacts distincts, `run_report.json`
  sans champ de trace, équation présente et annoncée non mesurée.

Suite complète : **258 passed** (235 avant ce module). `ruff check .` clean.

## Reproductibilité

```bash
uv run ruff check . && uv run pytest -q     # définition de terminé (CLAUDE.md)
uv run radar-run                            # écrit run_report.json ET run_trace.json
uv run python scripts/measure_human_baseline.py   # remplace les hypothèses par une mesure
```
