# Parallélisme, budgets & dégradation (module 4.3)

[`radar/concurrent_scoring.py`](src/radar/concurrent_scoring.py) : scoring
concurrent borné pour remplacer la boucle séquentielle de `ScoreStep`/
`run_pipeline` — sans changer leur contrat de sortie (même ordre, mêmes
scores). Câblé comme `ConcurrentScoreStep`, drop-in de `ScoreStep`, dans
[`radar/workflow.py`](src/radar/workflow.py).

## 1. Scoring concurrent, réassemblé dans l'ordre d'entrée

**Mécanisme** : `ThreadPoolExecutor` (I/O-bound — les appels LLM bloquent
sur le réseau, pas sur le CPU ; pas besoin d'``asyncio`` pour ce projet
entièrement synchrone). Les items sont traités par **lots** d'au plus
`max_concurrency`, chaque lot entièrement soumis puis attendu avant de
passer au suivant.

**Garantie d'ordre** : chaque résultat est associé à l'index de son item
d'origine ; la liste finale est explicitement triée par cet index avant
d'être renvoyée — indépendamment de l'ordre réel de complétion. Le test
décisif (`tests/test_concurrent_scoring.py::
test_concurrent_matches_sequential_under_variable_latency`) construit des
latences délibérément inversées (l'item 3 finit avant l'item 0) et vérifie
que la sortie concurrente est identique, item par item et dans l'ordre, à
la version séquentielle (`score_item` en boucle). Un second test
(`test_concurrent_preserves_input_order_across_multiple_batches`) vérifie
la même propriété sur plusieurs lots.

## 2. Budget dur (`max_cost_usd`)

**Branché sur le `UsageSink` du module 3.4** : avant de soumettre chaque
nouveau lot, le budget est vérifié via `usage_sink.total().cost_usd` —
aucun comptage de coût réinventé ici.

**Politique retenue : troncature propre, jamais d'exception.**
`ConcurrentScoreReport` renvoie les items scorés avec succès jusqu'au
dépassement, plus `n_skipped_budget` et `budget_exhausted=True` — les items
non tentés restent disponibles pour le prochain run (même sémantique que
`unseen[:max_scored]`, qui tronque déjà silencieusement sans lever). Lever
une erreur ferait perdre tout le travail déjà payé dans le run courant, ce
qu'aucune autre troncature de ce projet ne fait.

**Overshoot borné, pas illimité.** Le budget n'est vérifié qu'**entre**
deux lots — les appels déjà en vol dans un lot ne sont jamais interrompus
(pas d'annulation propre d'une requête HTTP en cours sans complexité
disproportionnée). Le dépassement possible est donc borné à
`max_concurrency` appels, jamais illimité. Testé :
`test_budget_truncates_cleanly_after_one_batch` (1 lot payé dépasse le
budget → le 2ᵉ lot n'est jamais soumis) et `test_zero_budget_skips_
everything_without_any_call` (budget déjà atteint dès le départ → aucun
appel).

## 3. Dégradation contrôlée : retry borné + backoff

**Seules les erreurs transitoires sont retentées** : `TransientLLMError`
(`radar/llm/errors.py`), une exception neutre au SDK — `AnthropicClient`
traduit les erreurs réelles `RateLimitError` (429) et `OverloadedError`
(529) en `TransientLLMError` ; tout le reste (bug de code, 400, auth...)
n'est jamais retenté. Testé au niveau SDK
(`tests/test_anthropic_client.py::
test_anthropic_client_translates_rate_limit_to_transient_error` et
`..._overloaded_...`, plus un test négatif avec `BadRequestError`) et au
niveau retry (`tests/test_concurrent_scoring.py::
test_non_transient_error_is_never_retried` : zéro retry, zéro appel à
`sleep`).

**Portée volontairement restreinte à 429/529** — exclusion assumée, pas un
oubli :
- `InternalServerError` (5xx génériques) : souvent transitoire en pratique,
  mais pas nommé explicitement dans la demande ; extension facile plus tard
  si l'expérience réelle le justifie.
- `APIConnectionError` (coupure réseau) : idem, hors périmètre de cette
  version.

**Backoff exponentiel plafonné** (`RetryPolicy`) :
`base_delay_seconds * 2**retries`, borné par `max_delay_seconds`.
`max_attempts` inclut la tentative initiale.

**Isolation, pas d'abort du lot.** Un item qui épuise ses retries (ou
échoue non-transitoirement) est compté dans `n_failures` et exclu de
`scored` — les autres items du lot et des lots suivants continuent, même
politique que le drafting existant (`DraftStep`/`run_pipeline`) : un échec
LLM isolé n'abat jamais tout le run. Testé :
`test_exhausts_retries_and_isolates_as_failure_without_raising`,
invariant `n_attempted == len(scored) + n_failures`
(`test_n_attempted_equals_scored_plus_failures_invariant`).

## 4. Décisions par défaut

| Paramètre | Valeur | Justification |
|---|---|---|
| `max_concurrency` | **5** | Pas de mesure de rate limit réel disponible (compte/tier non observés dans ce projet) — valeur prudente : ce radar plafonne déjà `max_scored=30` (module 1.x), donc 5 donne un vrai gain (6 lots au lieu de 30 appels séquentiels) sans risquer de saturer un tier d'API modeste. Réglable par appelant (`ConcurrentScoringConfig.max_concurrency`) ; à ajuster si des 429 réels sont observés en production. |
| `max_attempts` | **3** (1 essai + 2 retries) | Assez pour absorber un pic bref (rate limit, surcharge momentanée) sans faire attendre le pipeline indéfiniment sur un item bloqué. |
| `base_delay_seconds` | **0,5 s** | Delai initial court — un 429/529 se résorbe typiquement en une poignée de secondes. |
| `max_delay_seconds` | **8 s** | Plafonne la croissance exponentielle (0,5 → 1 → 2 → ... → 8) pour un pipeline qui reste borné en temps même en cas de dégradation soutenue. |
| Politique de budget | **Troncature propre** | Cf. §2 — cohérence avec `max_scored`, pas de perte du travail déjà payé. |

## 5. Intégration

`ConcurrentScoreStep` (`radar/workflow.py`) — même contrat de sortie que
`ScoreStep` (`state.scored`), bornée par `ConcurrentScoringConfig` en plus
de `PipelineConfig.max_scored` (inchangé, toujours la source de la
troncature amont). Testé comme remplacement direct dans une liste de
`Step` existante, avec résultat identique à `ScoreStep` sur `FakeLLM`
(`tests/test_radar_workflow_concurrent.py::
test_concurrent_score_step_is_a_drop_in_replacement_for_score_step`). Non
câblé dans `composition.py` — même portée que les modules 4.1/4.2 : une
capacité mesurée et testée, pas une migration de la production sans qu'on
le demande.

## Tests

- `tests/test_concurrent_scoring.py` (11 tests) : équivalence séquentiel/
  parallèle sous latences variables, borne de concurrence réellement
  observée (compteur thread-safe), budget (zéro, troncature, illimité),
  retry (succès après échecs, épuisement isolé, non-retry sur erreur non
  transitoire), invariant de comptage.
- `tests/test_anthropic_client.py` (+3 tests) : traduction SDK →
  `TransientLLMError` pour 429/529 uniquement, pas pour 400.
- `tests/test_radar_workflow_concurrent.py` (2 tests) : intégration comme
  `Step` drop-in, respect de `max_scored`.

```bash
uv run ruff check .
uv run pytest -q
```
