# CriticAgent — relecture post-rédaction (module 4.4)

## Décision

**Jeté.** Le CriticAgent (`radar/drafting/critic.py`) reste dans le dépôt,
testé (17 tests unitaires) et fonctionnel, mais **n'est pas câblé** comme
`Step` dans le workflow radar. Pas de boucle de réécriture bornée à
construire — la clause « si gardé » ne s'applique pas.

## 1. Contexte

Après la décomposition AngleAgent + WriterAgent (module 4.2), l'étape
suivante naturelle est un agent qui relit le brouillon déjà rédigé et le
rejette s'il présente un défaut réel : fait inventé, angle forcé, hors ligne
éditoriale, trop long. L'objectif explicite de ce module n'était pas de le
construire par principe, mais de **mesurer s'il apporte une valeur réelle**
avant de le câbler.

## 2. L'agent

[`radar/drafting/critic.py`](src/radar/drafting/critic.py) :
- `Verdict` (`accepted: bool`, `reasons: list[str]`).
- `check_length` : vérification **pure, sans LLM** — la longueur est un
  critère mécanique, aucun jugement requis (cohérent avec la grille
  d'arbitrage de `WORKFLOW.md` : pas de LLM là où une règle suffit).
- `build_critic_prompt` / `parse_verdict` / `critique_draft` : la frontière
  LLM ne couvre que les trois critères qui demandent un vrai jugement
  (fidélité, angle, ton). `critique_draft` court-circuite l'appel LLM si le
  défaut mécanique suffit déjà — pas de coût inutile.
- **Défaut sûr fail-closed** : sortie ambiguë ou vide → `REJETÉ`, jamais
  `ACCEPTÉ` à tort (même asymétrie de coût d'erreur que `QUALITY.md`/
  `ANGLE_AGENT.md`).

17 tests unitaires (`tests/test_critic_agent.py`) : heuristique de comptage
de phrases, parsing robuste (préfixe absent, raisons multiples, sortie
vide/ambiguë), court-circuit vérifié par un `LLMClient` factice qui lève une
`AssertionError` s'il est appelé.

## 3. Méthode de mesure

[`radar/eval/critic_test_set.py`](src/radar/eval/critic_test_set.py) : 14
brouillons — **6 bons, réutilisés tels quels** du run réel du module 4.2
(`draft_strategy_comparison.json`, déjà jugés bons dans `ANGLE_AGENT.md`) et
**8 volontairement défectueux**, deux par catégorie demandée, construits à
la main pour ce test (les articles sources restent réels).
[`scripts/measure_critic_agent.py`](scripts/measure_critic_agent.py) fait
tourner `critique_draft` avec de vrais appels LLM sur les 14 cas et calcule
taux de détection / taux de faux rejets.

**Bug rencontré et corrigé avant toute conclusion** : le premier run
utilisait `AnthropicClient()` sans préciser `max_tokens`, retombant sur le
défaut de 16 (dimensionné pour le scoring — un entier). Les raisons
étaient tronquées en plein mot (« Fait inventé - », « Ton non profession »).
Corrigé (`max_tokens=256`, même erreur déjà rencontrée pour le drafting en
3.3) et **re-mesuré avant d'écrire quoi que ce soit ci-dessous** — les
chiffres n'ont pas bougé (la troncature affectait les raisons affichées,
pas le verdict lui-même), mais le diagnostic de la cause réelle, ci-dessous,
n'était lisible qu'après correction.

## 4. Résultats chiffrés

| | Valeur |
|---|---|
| n | 14 (8 défectueux, 6 bons) |
| **Détection** | **8/8 (100 %)** |
| **Faux rejets** | **4/6 (67 %)** |
| Coût du run | 0,0103 USD |

Détail : [`critic_agent_measurement.json`](critic_agent_measurement.json).

**Détection parfaite par catégorie** : fait inventé 2/2, angle forcé 2/2,
hors-ligne éditoriale 2/2, trop long 2/2 (ces deux derniers sans aucun faux
positif observé sur les bons).

**Les 4 faux rejets, en détail** (Rozas, Goose, Base44, Just Eat Spain) —
tous invoquent « Angle forcé », et un aussi « Fait inventé » :
- *Goose* rejeté car le brouillon dit « vous gardez le contrôle de vos
  données, fini la dépendance aux API cloud » alors que le résumé fourni au
  critique dit seulement « un agent IA local » — le critique traite
  l'inférence raisonnable (exécution locale ⇒ pas de dépendance cloud)
  comme une fabrication.
- *Rozas* rejeté car « chaque demande traitée en 2 minutes » reformule
  « give every lead a 2-minute headstart » — une paraphrase discutable mais
  défendable, pas une invention.
- *Base44*, *Just Eat Spain* : même schéma — le critique exige que le lien
  PME soit **littéralement énoncé** dans le résumé source, sinon il le
  qualifie d'« artificiel ».

## 5. Analyse : pourquoi ça ne marche pas ici

**Ce n'est pas un artefact du protocole de test — c'est structurel.** Le
critique ne reçoit que `item.summary`, exactement le même résumé RSS court
(1-2 phrases) que le rédacteur a déjà utilisé pour écrire le brouillon :
c'est la **seule** matière que ce projet fait circuler (aucune étape ne
récupère l'article complet — cf. `radar/domain.py::RawItem`). Le critique
n'a donc structurellement pas plus d'information que le rédacteur pour
distinguer « reformulation raisonnable » de « fait inventé », ni pour juger
si le lien PME est honnête — c'est très exactement le travail que
l'AngleAgent (module 4.2) a déjà fait, avec le même niveau d'information.
Faire rejuger l'angle par un second agent, sur les mêmes données, ne peut
que dupliquer un jugement déjà pris ou le contredire au hasard — c'est ce
qu'on observe.

**Le critère « angle forcé » du critique est le principal responsable** : il
apparaît dans les 4 faux rejets. Les critères mécaniques (longueur) et de
ton (spam, anglais) n'ont, eux, produit **aucun** faux positif dans cette
mesure.

## 6. Décision argumentée

**Jeté**, sur les chiffres réels ci-dessus : un taux de faux rejets de 67 %
signifierait, en production, qu'un brouillon vraiment bon sur trois
survivrait au critique. Le radar produit déjà peu de brouillons
(`min_score=8`, calibré en 3.5, pour rester exigeant en amont) — un filtre
supplémentaire qui en supprime les deux tiers de plus annulerait
l'essentiel de la valeur du pipeline. La détection à 100 % ne compense pas :
elle porte sur des défauts grossiers (chiffres inventés, spam, longueur)
qu'un contrôle plus étroit capturerait déjà sans le faux-rejet massif — le
défaut n'est pas la détection, c'est le périmètre du jugement demandé
(fidélité + angle) appliqué avec la même information limitée que le
rédacteur.

**Piste non retenue ici, volontairement** : un critique restreint à la
longueur (déjà pure, zéro faux positif) et au ton/langue (zéro faux positif
mesuré), sans rejuger l'angle ni la fidélité factuelle fine, serait
probablement défendable — mais c'est un agent différent de celui spécifié,
et le mesurer proprement demanderait une nouvelle mesure dédiée. Je ne l'ai
pas fait ici pour ne pas retoucher le prompt jusqu'à obtenir un chiffre
acceptable : la mesure est celle du critique tel que spécifié, le verdict
lui correspond.

## Reproductibilité

```bash
uv run python scripts/measure_critic_agent.py
```

Écrit `critic_agent_measurement.json` (verdict + raisons par item, taux de
détection/faux rejets, coût réel).
