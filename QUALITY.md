# Calibration de `min_score` — held-out représentatif

> **Historique de révision** : la version précédente de ce document
> s'appuyait sur un held-out **rédigé à la main** (titres inventés, réalistes
> mais fictifs). Un jeu de calibration fictif ne prouve rien sur des données
> réelles : il a été remplacé par un held-out **réellement collecté**. Ce
> document est entièrement refait sur cette base : 30 items **réellement
> scrapés** depuis 7 flux RSS réels, lus et annotés à la main un par un.

## Claim

Sur un held-out **scellé de 30 items réellement scrapés** (pas rédigés),
couvrant les trois paliers de pertinence, `min_score = 8` obtient une
**précision de 100 % sur le palier « très pertinent »** (aucun item hors-sujet
ou moyen n'est jamais drafté), au prix d'un **rappel de 70 %** sur ce même
palier (3 items sur 10 vraiment pertinents sont scorés 7 par le modèle, juste
sous le seuil). Un contrôle indépendant sur 20 items réels non filtrés
confirme : **zéro faux positif**, à la fois dans le held-out et en conditions
réelles.

## 1. Source du held-out — réellement collecté

**Flux RSS testés et vérifiés par appel réseau réel** (`scripts/scrape_heldout_pool.py`) :

| Flux | URL | Statut |
|---|---|---|
| Zapier blog | `zapier.com/blog/feed/` | ✅ 25 items |
| n8n blog | `blog.n8n.io/rss/` | ✅ 15 items (nécessite le bundle CA `certifi`, cf. §5) |
| Blog du Modérateur — outils | `blogdumoderateur.com/tools/feed` | ✅ 12 items |
| Blog du Modérateur — marketing | `blogdumoderateur.com/marketing/feed` | ✅ 30 items |
| Blog du Modérateur — no-code | `blogdumoderateur.com/no-code/feed` | ✅ flux valide, 0 item ce jour-là |
| FrenchWeb | `frenchweb.fr/feed` | ✅ 100 items |
| Siècle Digital | `siecledigital.fr/feed/` | ✅ 20 items |
| Make.com blog | — | ❌ pas de RSS public trouvé (403 sur les chemins plausibles) |
| Alsacréations | `alsacreations.com/rss/actualites.xml` | ⚠️ flux réel (trouvé via les `<link rel="alternate">` de la page d'accueil) mais **sans `<pubDate>` par item** → 0 item après `parse_rss` (le parseur exige une date ; non modifié, hors périmètre) |
| Newsletters d'intégrateurs | — | ❌ pas de RSS public identifié (les newsletters sont typiquement email-only) |

**Pool brut collecté : 202 items réels, dédupliqués.** Les 30 items du
held-out sont **sélectionnés** dans ce pool (pas rédigés), avec les titres,
résumés et dates de publication exacts du scrape. Sélection + labels :
[`scripts/label_heldout_pool.py`](scripts/label_heldout_pool.py) — chaque URL
est un article réel et vérifiable.

**Zones grises évitées.** Les labels 3–4 et 7 sont volontairement absents du
held-out (paliers nets pour un tableau precision/rappel lisible) — mais pas
du pool : ce sont des scores réels que le modèle attribue (cf. §3 et §4).

**Limite honnête sur le mélange de sources.** Zapier et n8n publient en
anglais ; le prompt de scoring (`radar/scoring.py`) est en français et cible
une audience PME française. Le held-out contient donc un mélange
anglais/français, fidèle aux flux réellement disponibles pour ce thème (il
n'existe pas de blog Zapier/n8n en français) — pas un choix arbitraire.

**Schéma scellé** (`RawItem` + `label`, aucun champ pour un score modèle) :
[`src/radar/eval/heldout_representative.json`](src/radar/eval/heldout_representative.json).
Les labels ont été fixés en lisant le contenu réel scrapé, **avant** toute
exécution du scorer sur ce jeu (vérifié par
`tests/test_heldout_representative.py`).

## 2. n total et distribution des labels

**n = 30**, sélectionnés pour couvrir également les trois paliers :

| Palier | Labels visés | n | Labels réels obtenus |
|---|---|---|---|
| Hors-sujet | 0–2 | 10 | 0 (×8), 1 (×2) |
| Moyen | 5–6 | 10 | 5 (×7), 6 (×3) |
| Très pertinent | 8–10 | 10 | 8 (×5), 9 (×4), 10 (×1) |

## 3. Tableau précision/rappel par seuil

Mesuré avec `precision_at_threshold`/`recall_at_threshold`
([`radar/eval/metrics.py`](src/radar/eval/metrics.py)) — convention
« retenu » = `score >= seuil`, « pertinent » = `label >= seuil` (même seuil
des deux côtés, cf. docstring des fonctions) — sur les vraies prédictions du
modèle (`claude-haiku-4-5`, run réel via `scripts/calibrate_threshold.py`) :

| Seuil (`min_score`) | Précision | Rappel |
|---|---|---|
| 4 | 100,0 % | 90,0 % |
| 5 | 100,0 % | 85,0 % |
| 6 | 81,3 % | 100,0 % |
| 7 | 76,9 % | 100,0 % |
| 8 | **100,0 %** | 70,0 % |

**Lecture importante.** À seuil bas (4-5), la précision affichée est
mécaniquement élevée : la définition de « pertinent » descend avec le seuil
(à 4, « pertinent » = `label >= 4`, ce qui inclut tout le palier moyen). Ce
n'est donc pas la preuve qu'un seuil bas exclut le contenu non actionnable —
juste qu'il n'inclut pas les items hors-sujet (dont le score plafonne à 2).
Pour la vraie question de calibration (« est-ce que je ne drafte QUE du
contenu vraiment actionnable ? »), la mesure utile est la précision par
rapport au palier fixe **« très pertinent » (label ≥ 8)**, calculée
directement sur `quality_calibration.json` :

| Seuil | Items retenus | Précision (vs. label ≥ 8) | Rappel (vs. label ≥ 8) |
|---|---|---|---|
| 4 | 18 | 55,6 % | 100 % |
| 5 | 17 | 58,8 % | 100 % |
| 6 | 16 | 62,5 % | 100 % |
| 7 | 13 | 76,9 % | 100 % |
| 8 | 7 | **100 %** | 70 % |

Sur ce plan-là, seul `min_score = 8` atteint 100 % de précision — tous les
seuils inférieurs laissent passer une majorité de contenu « moyen », pas
franchement actionnable, aux côtés du contenu vraiment pertinent.

**Ce qui se passe au seuil 7 → 8.** Trois items vraiment pertinents (label
8-9) sont scorés **7** par le modèle : *« The Zappy Award winner behind Just
Eat Spain's faster partner onboarding »*, *« RPA vs. Workflow Automation »*,
*« Workflow Versioning for Reliable Automation and Maintenance »* — trois cas
limites, du contenu solide mais un peu plus « pratique/éducatif » que « outil
concret ». Dans le même temps, trois items du palier moyen (label 6) sont
*eux aussi* scorés **7** : *« Le véritable frein à l'adoption de l'IA... »*,
*« Réforme de la facturation électronique... »*, *« Building France invite
les entrepreneurs... »*. **Le score 7 est un palier bruité** : il mélange de
vrais positifs sous-notés et de vrais négatifs sur-notés, dans les deux
sens. On ne peut pas lui faire confiance pour trancher.

## 4. Contrôle indépendant : échantillon réel non filtré (point 4)

Le batch exact des 20 items du run réel de module 3.3 **n'a pas été
conservé** — `PipelineReport` ne persiste que des compteurs agrégés
(`n_fetched`, `n_scored`...), pas la liste des items eux-mêmes, et
`.data/seen.json` n'enregistre que les items **draftés** (aucun ce jour-là).
Impossible de le reconstituer a posteriori.

**Substitut honnête** : les 20 items **les plus récents, non sélectionnés**
dans le held-out ci-dessus, issus du même scrape réel — un échantillon **non
biaisé** (aucune curation vers un palier de label), donc plus proche de ce
qu'un run réel produit aujourd'hui avec les flux enrichis que ne l'aurait été
une nouvelle sélection à la main. Jeu :
[`src/radar/eval/production_recall_check.json`](src/radar/eval/production_recall_check.json),
labels : [`scripts/label_production_recall_check.py`](scripts/label_production_recall_check.py).

Résultat réel (`scripts/check_production_recall.py`,
`production_recall_check_results.json`) :

| | Valeur |
|---|---|
| n | 20 |
| Items vraiment pertinents dans l'échantillon (label ≥ 8) | **0** |
| Items retenus par `min_score = 8` | **0** |
| Faux positifs à ce seuil | **0** |
| Score modèle maximal observé | 7 |

**Constat honnête, dans les deux sens.** Le rappel n'est pas mesurable sur
cet échantillon (aucun vrai positif à retrouver) — même avec des flux
automation/no-code dans `FEED_URLS`, le contenu réellement actionnable reste
minoritaire dans le flux brut du jour ; il a fallu chercher dans 202 items
pour en réunir 10 pour le held-out. En revanche, la précision tient : zéro
faux positif, y compris sur des articles Zapier au ton engageant qui
mentionnent l'automatisation sans être des guides d'automatisation concrets
(ex. *« How to add Zoom to Google Calendar »*, scoré 7 par le modèle contre
un label humain de 3 — écart notable, mais toujours sous le seuil de 8).

## 5. Seuil retenu et justification

**`min_score = 8`** (inchangé depuis la première version calibrée de ce
module — mais désormais justifié sur des données réelles, pas fabriquées).

Trois justifications convergentes :

1. **Empirique (palier fixe « très pertinent »)** : seul `min_score = 8`
   atteint 100 % de précision par rapport au palier réellement actionnable ;
   tous les seuils inférieurs laissent passer 25 à 45 % de contenu moyen.
2. **Empirique (robustesse)** : confirmé à zéro faux positif sur un second
   échantillon réel, non filtré, non curaté (§4).
3. **Sémantique (grille de notation)** : `radar/scoring.py::build_prompt`
   définit `7 = « utile mais pas directement actionnable »` et `8 = « gain
   réel »`. Les données réelles renforcent cet argument plutôt que
   l'affaiblir : le score 7 s'avère être un palier **bruité** où se
   mélangent vrais positifs sous-notés et vrais négatifs sur-notés (§3) — on
   ne peut pas s'y fier pour distinguer les deux. Exiger 8 revient à ne
   jamais trancher sur ce palier ambigu.

**Coût du changement (rappel 70 %, pas 100 %)** : accepté consciemment.
Manquer un item pertinent sur 10 signifie qu'il n'est pas drafté ce run-là —
coût faible (le flux est quotidien, l'article n'a pas disparu). Drafter du
contenu non actionnable coûte plus cher : temps de relecture, confiance dans
l'automatisation érodée. L'asymétrie favorise la précision.

## 6. Portée (honnête)

- **n = 30 pour le held-out de calibration, n = 20 pour le contrôle** : des
  échantillons de cette taille donnent des intervalles de confiance larges
  (une seule erreur de plus ou de moins déplace la précision de plusieurs
  points). Les tendances (7 = palier bruité, 8 = coupure nette) sont notées
  sur des effectifs faibles par item concerné (3 sur 10) — à revalider si le
  volume de trafic PME-automation augmente.
- **Mélange anglais/français** (§1) : le prompt de scoring n'a pas été
  spécifiquement testé pour la robustesse cross-langue ; les résultats
  ci-dessus ne l'isolent pas comme facteur.
- **Le rappel n'est mesuré que sur le held-out curé**, pas sur un vrai flux
  de production à volume élevé — le contrôle §4 confirme l'absence de faux
  positifs mais ne peut rien dire sur le rappel réel (0 vrai positif observé
  ce jour-là).
- Complète [`HELDOUT.md`](HELDOUT.md) (qui valide la **spécificité**
  hors-échantillon du scorer sur une source inédite, Numerama) sans le
  remplacer : les deux jeux mesurent des choses différentes.

## 7. Date de mesure

**2026-08-29**, avec `claude-haiku-4-5` (modèle de production).

## Reproductibilité

```bash
uv run python scripts/scrape_heldout_pool.py          # pool réel (réseau)
uv run python scripts/label_heldout_pool.py            # applique les 30 labels
uv run python scripts/label_production_recall_check.py # applique les 20 labels
uv run python scripts/calibrate_threshold.py            # precision/rappel (LLM)
uv run python scripts/check_production_recall.py        # contrôle indépendant (LLM)
```

- Non-contamination testée : `tests/test_heldout_representative.py`,
  `tests/test_production_recall_check.py` (schéma scellé, disjoint du
  dataset d'entraînement, disjoint l'un de l'autre, couverture des paliers).
- Métriques testées : `tests/test_metrics.py`.
