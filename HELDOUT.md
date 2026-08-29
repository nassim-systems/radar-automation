# Évaluation out-of-sample (held-out)

## Claim

Le scorer de pertinence PME, évalué **hors-échantillon** sur **15 articles d'une
source jamais vue à l'entraînement** (Numerama — held-out figé et annoté à la
main), obtient un **agreement de 0,93** et une **corrélation de rang de Spearman
de 0,87** avec les labels humains.

## Métriques

| Métrique | Valeur | n |
|---|---|---|
| Agreement (`1 − MAE/10`) | **0,9333** | 15 |
| Spearman (corrélation de rang) | **0,8693** | 15 |

## Portée (honnête)

Ce held-out est **dominé par du contenu non pertinent** (tech / actualité
généraliste) — labels majoritairement 0-2. La métrique valide donc surtout la
**spécificité** du scorer :

- il **ne sur-note pas l'hors-sujet** (les 8 items clairement hors-sujet →
  `human_label = 0`, `model_score = 0`) ;
- il **préserve le classement** des rares items un peu plus pertinents.

Elle **ne démontre pas encore** la capacité du scorer à **discriminer finement
de vrais positifs PME** : cela nécessiterait un held-out plus riche en items
pertinents (piste « élargir le held-out avec de vrais positifs et des cas
limites »).

**Suite (module 3.5)** : [`QUALITY.md`](QUALITY.md) comble ce manque avec un
second held-out, construit celui-là pour couvrir les trois paliers de
pertinence (hors-sujet / moyen / très pertinent), et l'utilise pour calibrer
`min_score` par précision/rappel plutôt qu'au jugé.

## Reproductibilité

- Jeu figé et annoté : [`src/radar/eval/heldout_labeled.json`](src/radar/eval/heldout_labeled.json)
  (15 items `RawItem + label`, labels humains validés).
- Recalcul (vrais appels LLM, hors suite de tests) :

  ```bash
  uv run python scripts/eval_heldout.py
  ```

  Écrit le détail par item (`human_label` / `model_score`) et les métriques dans
  `heldout.json`.
