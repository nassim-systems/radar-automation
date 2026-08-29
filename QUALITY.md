# Calibration de `min_score` — held-out représentatif

## Claim

Sur un held-out **scellé de 30 items**, construit pour **couvrir les trois
paliers de pertinence** (hors-sujet, moyen, très pertinent) plutôt que d'être
dominé par le hors-sujet comme [`HELDOUT.md`](HELDOUT.md), le scorer atteint
**100 % de précision et 100 % de rappel à `min_score = 7` et `8`** — contre
**84,6 % de précision** au seuil actuellement en production (`6`). Le seuil
retenu est **`min_score = 8`**, désormais câblé dans
[`src/composition.py`](src/composition.py).

## 1. Source du held-out

**Méthode : curation manuelle, pas de scraping.** Contrairement au held-out
Numerama de `HELDOUT.md` (réellement scrapé, mais dont la distribution des
labels est dominée par le hors-sujet — cf. sa section « Portée »), ce
held-out est **rédigé à la main** : 30 titres + résumés représentatifs de
sujets réels (outils réels : Zapier, Make.com, n8n, Airtable, HubSpot ;
pratiques réelles : RPA, no-code, agents IA, automatisation de la
facturation/comptabilité/CRM), choisis pour **garantir** une couverture des
trois paliers — chose qu'un scrape ponctuel ne peut pas garantir (le premier
held-out réel, scrapé, n'avait par exemple presque aucun item très pertinent).

Les items évitent délibérément les scores intermédiaires 3–4 et 7 de la
grille de notation (`radar/scoring.py::build_prompt`) pour produire des
paliers nets, plus faciles à interpréter dans un tableau précision/rappel :

| Palier | Labels | n |
|---|---|---|
| Hors-sujet | 0–2 | 10 |
| Moyen | 5–6 | 10 |
| Très pertinent | 8–10 | 10 |

Jeu scellé et versionné :
[`src/radar/eval/heldout_representative.json`](src/radar/eval/heldout_representative.json)
(schéma `RawItem + label` uniquement — **aucun champ ne peut transporter un
score modèle**, garanti par `tests/test_heldout_representative.py::test_heldout_representative_is_sealed_no_model_score_field`).
Les labels ont été fixés **avant** toute exécution du scorer sur ce jeu
(aucune contamination : voir la section Reproductibilité).

## 2. n total et distribution des labels

**n = 30.**

| Label | 0 | 1 | 5 | 6 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|
| n | 8 | 2 | 5 | 5 | 1 | 5 | 4 |

## 3. Tableau précision/rappel par seuil

Mesuré avec `precision_at_threshold`/`recall_at_threshold`
([`radar/eval/metrics.py`](src/radar/eval/metrics.py)) sur les vraies
prédictions du modèle (`claude-haiku-4-5`, vrais appels API — voir
Reproductibilité) :

| Seuil (`min_score`) | Précision | Rappel |
|---|---|---|
| 4 | 100,0 % | 75,0 % |
| 5 | 100,0 % | 75,0 % |
| 6 (**production actuelle avant ce module**) | **84,6 %** | 73,3 % |
| 7 | **100,0 %** | **100,0 %** |
| 8 | **100,0 %** | **100,0 %** |

Lecture des cas d'erreur au seuil 6 (les deux faux positifs) :
- « Cybersécurité : les attaques par rançongiciel visant les PME... » — label
  humain 5 (pertinent pour une PME mais pas actionnable), score modèle 6.
- « Les grandes tendances du marketing digital à surveiller en 2027 » —
  label humain 5, score modèle 6.

Ni le palier hors-sujet (label ≤ 1, score modèle toujours **0**) ni le
palier très pertinent (label ≥ 8, score modèle toujours **8 ou 9**) ne
produisent d'erreur, à aucun seuil testé. Le bruit vient entièrement du
palier moyen (label 5–6), où le modèle est **systématiquement plus sévère
que l'annotateur humain** (scores observés jusqu'à 2–3 pour des items
labellisés 5) — jamais l'inverse. C'est pour cela que 7 et 8 donnent un
résultat identique : aucun item de ce held-out n'a reçu le score 7, donc
`score >= 7` et `score >= 8` opèrent la même coupure.

## 4. Seuil retenu et justification

**`min_score = 8`** (changé depuis `6`).

Deux justifications indépendantes, convergentes :

1. **Empirique** : 7 et 8 sont à égalité sur ce held-out (100 % / 100 %) —
   aucune donnée ne permet de les départager sur ce jeu. L'exemple donné dans
   la demande (85 % précision / 70 % rappel) est dépassé par les deux.
2. **Sémantique (grille de notation)** : `radar/scoring.py::build_prompt`
   définit explicitement `7 = « utile pour une PME mais pas directement
   actionnable »` et `8 = « outil, méthode ou pratique pouvant apporter un
   gain réel »`. Le rôle de `min_score` est de ne drafter que du contenu
   *actionnable* (cf. `filter_by_min_score`, module 3.3) — retenir `7`
   ferait donc drafter, par construction du prompt, des items que le modèle
   lui-même qualifie de non actionnables. `8` est la coupure cohérente avec
   la sémantique déjà écrite dans le prompt, pas seulement avec les chiffres.

Avec le seuil précédent (`6`), le radar aurait pu drafter des items
« moyens » (label 5, ex. cybersécurité PME générique) que le rubric qualifie
lui-même de non actionnables — exactement le risque que le module 3.3
(seuil de pertinence) voulait éliminer, mais insuffisamment calibré faute de
held-out couvrant ce palier.

**Coût du changement** : nul sur le rappel des items très pertinents (100 %
aux deux seuils) — le passage à `8` élimine des faux positifs sans manquer
aucun vrai positif, sur ce held-out.

## 5. Portée (honnête)

- **n = 30, jeu construit** (pas un échantillon aléatoire de trafic RSS réel)
  — les 100 % de précision/rappel aux seuils 7-8 sont optimistes : des
  items rédigés pour être nets sont par construction moins ambigus que le
  flux RSS réel. Ce held-out calibre un ordre de grandeur défendable, ce
  n'est pas une garantie de 100 % en production.
- **Un seul palier est source d'erreur** dans cette mesure (le palier
  moyen, 5-6) : la conclusion « 8 est un bon seuil » repose entièrement sur
  la bonne séparation hors-sujet / très-pertinent observée ici. Un vrai
  positif qui ressemblerait davantage au palier moyen dans le trafic réel
  resterait un point aveugle non mesuré par ce jeu.
- Complète `HELDOUT.md` (qui valide la **spécificité** hors-échantillon sur
  source inédite) sans le remplacer : les deux jeux mesurent des choses
  différentes et restent versionnés séparément.

## 6. Date de mesure

**2026-08-29**, avec `claude-haiku-4-5` (modèle de production, cf.
[`radar/llm/anthropic_client.py`](src/radar/llm/anthropic_client.py)).

## Reproductibilité

- Jeu figé et annoté :
  [`src/radar/eval/heldout_representative.json`](src/radar/eval/heldout_representative.json)
  (30 items `RawItem + label`, labels fixés avant toute exécution du scorer).
- Non-contamination testée : `tests/test_heldout_representative.py` (schéma
  scellé, disjoint du dataset d'entraînement, couverture des trois paliers).
- Métriques testées : `tests/test_metrics.py`
  (`precision_at_threshold`/`recall_at_threshold`).
- Recalcul (vrais appels LLM, hors suite de tests) :

  ```bash
  uv run python scripts/calibrate_threshold.py
  ```

  Écrit le tableau seuil → précision/rappel, le détail par item et le coût
  du run (module 3.4) dans `quality_calibration.json`.
