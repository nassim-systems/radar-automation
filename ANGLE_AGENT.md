# AngleAgent + WriterAgent — décomposition du drafting (module 4.2)

## Décision

**Gardé.** Câblé comme `AngleStep` + `WriteStep` dans
[`radar/workflow.py`](src/radar/workflow.py)
(`build_radar_steps_decomposed`). Pas câblé dans `composition.py` /
`run_pipeline` (production) au moment de ce module — cf. « Portée » en fin de
document. **Mise à jour (module 4.5)** : `AngleStep`/`WriteStep` sont
désormais en production, via `build_radar_steps_production` — voir
`MIGRATION.md`.

## 1. Contexte

Le mono-appel actuel (`build_draft_prompt`) fait deux choses en un seul
appel LLM : décider s'il existe un angle PME et rédiger le post. Le run réel
du module 3.3 avait révélé un symptôme : un article sur des batteries
domestiques pour data centers, noté 1/10 de pertinence, s'était vu attribuer
un post forçant un lien PME artificiel (« *Cette initiative pourrait offrir
aux PME une nouvelle opportunité...* »). Le mono-appel n'a pas la
possibilité de répondre « il n'y a rien d'honnête à en tirer » — il doit
toujours produire du texte.

## 2. Les deux agents

- [`radar/drafting/angle.py`](src/radar/drafting/angle.py) : `Angle`
  (`has_angle: bool`, `angle: str | None`), `build_angle_prompt`,
  `parse_angle`, `decide_angle`. Ne rédige rien — juge uniquement s'il
  existe un angle honnête.
- [`radar/drafting/writer.py`](src/radar/drafting/writer.py) :
  `build_writer_prompt`, `write_draft`. Ne décide plus de l'angle — rédige
  à partir de celui fourni par l'`Angle`. Réutilise `parse_draft` existant
  (aucun parsing dupliqué).

Chaque agent a sa frontière LLM propre, testée isolément avec `FakeLLM`
(`tests/test_angle_agent.py`, `tests/test_writer_agent.py` — 16 tests :
parsing robuste sur préfixe/marqueur absent, réponse vide, sortie
multiligne, verdicts différents scénarisés par item).

## 3. Méthode de mesure

[`scripts/compare_draft_strategies.py`](scripts/compare_draft_strategies.py)
exécute les deux stratégies, avec de vrais appels LLM, sur les **10 items
« très pertinents » (label ≥ 8)** du held-out scellé du module 3.5
(`heldout_representative.json`) — la population réelle qui atteint l'étage
de rédaction en production (`min_score = 8`). Résultat brut :
[`draft_strategy_comparison.json`](draft_strategy_comparison.json).

**Métrique de qualité** : jugement humain sur chaque brouillon (0–2 par
critère, moi-même comme annotateur — même limite de non-indépendance que
partout ailleurs dans ce projet, cf. `QUALITY.md`) :
- **Fidélité** : aucun fait inventé, cohérent avec l'article.
- **Naturel de l'angle** : le lien PME est-il honnête ou senti comme forcé ?
- **Actionnabilité** : le lecteur repart-il avec quelque chose de concret ?

## 4. Résultats chiffrés

**Coût réel** (`ListUsageSink`, module 3.4) :

| | Tokens in/out | Coût USD |
|---|---|---|
| Mono (10 appels) | 2 235 / 1 340 | 0,0089 |
| Décomposé (10 angle + 9 write) | 5 927 / 1 796 | 0,0149 |

**×1,67, pas ×2** : le skip d'un item sans angle honnête économise un appel
de rédaction — le surcoût n'est pas un doublement mécanique, il dépend de la
part d'items sans angle honnête.

**Qualité (0–6, deuxième relecture plus stricte — ma première passe était
trop généreuse et donnait un score presque uniforme)** :

| # | Item | Mono | Décomposé | Écart |
|---|---|---|---|---|
| 1 | Best automation software for SMB | 5 | 6 | +1 |
| 2 | Rozas (Zapier) | 5 | 5 | 0 |
| 3 | Zapier MCP | 4 | 6 | +2 |
| 4 | Just Eat Spain onboarding | 6 | 5 | **−1** |
| 5 | Amazon Bedrock AgentCore | 4 | *(aucun brouillon)* | angle jugé absent |
| 6 | RPA vs Workflow Automation | 5 | 6 | +1 |
| 7 | Workflow Versioning | 6 | 6 | 0 |
| 8 | Goose | 6 | 6 | 0 |
| 9 | Base44 | 6 | 6 | 0 |
| 10 | Scraper Studio | 6 | 5 | **−1** |
| | **Moyenne** | **5,4** (n=10) | **5,67** (n=9, item 5 non noté) | +0,27 |

**Lecture honnête** : sur la seule moyenne, l'amélioration est **faible et
non uniforme** — deux items (4, 10) sont même légèrement *moins* actionnables
côté décomposé (l'angle plus élaboré tire parfois vers une conclusion plus
abstraite que la traduction directe « pour une PME, cela signifie... » du
mono-appel). Sur 6 des 10 items, l'écart de qualité est nul ou marginal. Un
comparatif ne regardant *que* la moyenne ne justifierait pas clairement le
surcoût de ×1,67.

**Ce qui justifie la décision n'est pas la moyenne — c'est l'item 5.**
L'AngleAgent a jugé, sur un article réel de ce même run (multi-agents avec
mémoire client sur AWS Bedrock), qu'aucun angle PME honnête n'existait, et a
**skippé** — reproduisant exactement, sur un exemple frais et indépendant du
symptôme historique de 3.3, la défaillance que ce module devait corriger.
Le mono-appel, lui, a rédigé quand même, avec une conclusion sentie comme
plaquée (« *une expérience client plus fluide et efficace, même pour les
PME* » — noté 4/6, perdant un point sur le naturel de l'angle).

## 5. Décision argumentée

**Gardé**, pour trois raisons, dans cet ordre d'importance :

1. **Asymétrie du coût d'erreur, pas la moyenne.** Comme déjà établi dans
   `QUALITY.md` (calibration de `min_score`) : un brouillon manqué coûte
   peu (rien n'est publié, on retente), un brouillon forcé et publié coûte
   plus cher (crédibilité érodée). L'item 5 est la preuve, sur ce run,
   que la décomposition élimine ce risque précis — même si la moyenne de
   qualité ne progresse que marginalement ailleurs.
2. **Coût absolu négligeable à l'échelle réelle du projet.** ×1,67 sur un
   run qui drafte 0 à quelques items (les runs réels de 3.3/3.4/3.5 ont
   tous drafté 0 item) représente quelques millièmes de dollar par run.
   Le ratio relatif (×1,67) est correct mais trompeur si on l'extrapole
   sans regarder le volume réel.
3. **Observabilité gratuite.** L'angle devient un artefact explicite et
   inspectable (`Angle.has_angle`/`Angle.angle`) au lieu d'être une
   décision implicite noyée dans un seul appel — cohérent avec l'esprit du
   module 4.1 (traçabilité par étape).

**Alternative moins chère envisagée, non retenue pour cette mesure** :
ajouter au prompt mono-appel une option explicite « si aucun lien PME
honnête, réponds AUCUN BROUILLON » capturerait peut-être l'essentiel du
bénéfice de l'item 5 sans surcoût. Je ne l'ai pas testée — c'est une piste
de suivi légitime, pas un argument contre la décomposition telle que
mesurée ici.

**Ce que cette mesure ne prouve pas** : à n=10, l'écart de moyenne (+0,27)
n'a aucune robustesse statistique. Si l'objectif avait été « la
décomposition rend chaque brouillon meilleur », la réponse mesurée serait
plutôt non. L'objectif réellement atteint est plus étroit : « la
décomposition empêche la pire erreur possible (un angle forcé) sans jamais
produire un résultat clairement pire sur l'ensemble ».

## 6. Intégration

`AngleStep` et `WriteStep` (`radar/workflow.py`) remplacent `DraftStep` dans
`build_radar_steps_decomposed` — même isolation des échecs LLM item par
item, même politique `mark_seen` (un item sans angle honnête reste « à
voir », retenté au run suivant, exactement comme un échec de draft).
Testé : `tests/test_radar_workflow_decomposed.py` (ordre des étapes, skip
effectif, non-marquage des items skippés, capture d'usage à travers
score+angle+write).

**Portée (au moment de ce module)** : non câblé dans
`composition.py::build_radar_pipeline` (production, toujours `run_pipeline`
+ mono-appel). Cohérent avec la portée déjà posée dans `WORKFLOW.md` : ce
module ajoute une capacité mesurée et testée, il ne migre pas le chemin de
production sans qu'on le demande.

**Mise à jour (module 4.5, `MIGRATION.md`)** : le chemin de production a
depuis été consolidé sur ce workflow — `AngleStep`/`WriteStep` sont
désormais câblés dans `composition.py` via `build_radar_steps_production`,
et `run_pipeline` a été supprimée.

## Reproductibilité

```bash
uv run python scripts/compare_draft_strategies.py
```

Écrit `draft_strategy_comparison.json` (brouillons des deux stratégies +
coût réel). Le jugement de qualité (tableau §4) est une relecture manuelle
de ce fichier, pas un calcul automatisé.
