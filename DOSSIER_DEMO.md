# Radar Automation — dossier de démonstration

**Un système de veille qui lit, trie et rédige seul, pour deux centimes par
jour — et dont chaque brique a été mesurée avant d'être gardée.**

*Khirami — Nassim · Données au 1ᵉʳ septembre 2026 · Lecture : 10 minutes*

> **Comment lire ce dossier.** Chaque section donne d'abord son **verdict**
> en une phrase, puis la **preuve chiffrée** qui le soutient, puis un renvoi
> vers l'**annexe** pour qui veut vérifier. Les neuf sections se lisent sans
> connaissance technique ; les annexes sont faites pour être auditées.

---

## 1 — Le verdict en une page

> **Verdict.** Trois runs réels sur quatre jours, aucun échec, quatre
> centimes de coût total. Le système fonctionne sans surveillance et rend
> compte de tout ce qu'il fait.

**Preuve.**

| | Valeur | Source |
|---|---|---|
| Runs réels enregistrés | **3** (29/08, 30/08, 01/09) | `docs/run_history.json` |
| Articles traités par run | 17 à 57 selon le jour | idem |
| Coût d'un run | **0,0082 $ à 0,0214 $** | idem |
| Coût cumulé des trois runs | **≈ 0,040 $** | idem |
| Appels au modèle | 73 | idem |
| Échecs | **0 sur 73** | idem |
| Durée d'un run complet | **3,8 s** (run tracé du 01/09) | `run_trace.json` |
| Précision du filtre éditorial | **100 %**, zéro faux positif | `QUALITY.md` |
| Tests automatisés au vert | **264** | suite du dépôt |
| Décisions d'architecture chiffrées | **7, dont 1 refus** | 7 documents |

*Annexe A1 — `run_report.json`, `run_trace.json`, `docs/run_history.json`.*

---

## 2 — Le problème, en coût humain

> **Verdict.** Le travail que ce système remplace est un travail de lecture
> et de tri : long, quotidien, et sans valeur ajoutée tant qu'on n'a rien
> trouvé. Le système le fait en quelques secondes pour un coût qui
> n'apparaît pas sur une facture.

**Preuve — le run tracé du 1ᵉʳ septembre, 17 articles.**

| | Un humain | Le système |
|---|---|---|
| Récupérer 17 articles sur 7 flux | ~2 min | 0,42 s |
| Lire et juger la pertinence de chacun | 17 × ~25 s ≈ **7 min** | 3,34 s |
| Décider | inclus | inclus |
| **Total** | **≈ 7 min 5 s** | **3,8 s** |
| Coût (50 €/h chargés) | **5,90 €** | **0,0075 €** |

Facteur de compression du temps : **×112**.

> ⚠️ **Statut de ces chiffres.** Les 25 secondes de tri par article et le
> coût horaire de 50 € sont des **hypothèses déclarées**, pas des mesures :
> le système sait mesurer sa propre latence, il ne sait pas mesurer la
> vôtre. Le fichier de sortie porte cette distinction explicitement
> (`value.baseline.measured = false`). Seule la colonne « le système » est
> mesurée. Remplacez les hypothèses par vos propres chiffres : l'équation
> est paramétrique et livrée avec le système.

**Sur un run productif** (30 août : 30 articles triés, 3 brouillons rédigés),
la même équation donne ≈ **36 minutes** de travail humain, dont ≈ 2 minutes
de relecture qui restent à votre charge — soit ≈ **28,50 €** de temps évité
pour 0,02 € de coût machine. Projection, pas mesure : la latence de ce
run-là n'a pas été instrumentée.

*Annexe A4 — `OBSERVABILITY.md` §4, paramètres et limites de l'équation.*

---

## 3 — Trois runs réels, de bout en bout

> **Verdict.** Ce ne sont pas des démonstrations scénarisées : trois
> exécutions datées, sur des flux publics, rejouables par vous.

**Preuve — l'historique complet, sans sélection.**

| Date | Récupérés | Frais | Notés | Au-dessus du seuil | Rédigés | Appels | Échecs | Coût |
|---|---|---|---|---|---|---|---|---|
| 29/08 | 20 | 20 | 20 | 0 | 0 | 20 | 0 | 0,0106 $ |
| 30/08 | 57 | 32 | 30 | **3** | **3** | 36 | 0 | 0,0214 $ |
| 01/09 | 17 | 17 | 17 | 0 | 0 | 17 | 0 | 0,0082 $ |

**Deux runs sur trois n'ont rien produit — et c'est le comportement voulu.**
Le seuil de pertinence est calibré pour ne jamais rédiger sur un article
médiocre (§5). Un jour sans article vraiment actionnable est un jour sans
publication, pas un jour d'échec. Un système qui produirait trois posts
chaque jour, quoi qu'il arrive, serait un système qui force ses sujets.

**L'entonnoir du run productif (30 août).**

```
57 récupérés  →  57 dédupliqués  →  32 récents (< 7 j)  →  32 jamais vus
   →  30 notés (plafond de budget)  →  3 au-dessus du seuil  →  3 rédigés
```

36 appels au modèle : 30 notations + 3 décisions d'angle + 3 rédactions.
Le compte tombe juste à l'appel près, et le système le vérifie lui-même.

**Un brouillon réel, tel que produit** (score 8/10) :

> *Source : « Claude integrations: How to use Zapier with Claude », Zapier,
> 26/08 — [zapier.com/blog/automate-claude](https://zapier.com/blog/automate-claude)*
>
> « Connecter Claude à vos outils métier via Zapier, c'est transformer vos
> workflows existants sans coder. Plutôt que de discuter avec Claude en mode
> conversationnel, l'automatisation via Zapier vous permet de chaîner des
> tâches complètes : enrichir vos contacts CRM, générer des emails
> personnalisés, traiter vos bases de données. Découvrez comment intégrer
> l'intelligence de Claude directement dans vos processus métier pour gagner
> du temps sur les tâches répétitives. »

À juger sur sa **fidélité à la source**, pas sur son style : c'est une
matière première à valider en trente secondes, pas un post publié (§7).

*Annexe A2 — les trois brouillons du 30/08 et leurs articles sources.*

---

## 4 — Architecture : ce que j'ai choisi de **ne pas** faire

> **Verdict.** Ce système n'est pas « une architecture multi-agents ». Il est
> déterministe partout où la séquence est connue d'avance, et n'appelle un
> modèle que là où il faut réellement juger. C'est ce qui le rend prévisible,
> auditable et bon marché.

**Preuve — la grille d'arbitrage appliquée à chaque étape.**

| | Qui décide l'étape suivante | Coût / latence | Auditabilité |
|---|---|---|---|
| Flux déterministe | le code | minimal | le code *est* la trace |
| **Orchestration explicite** ← retenu | le code, mais réifié | minimal | **trace par étape, gratuite** |
| Agents (boucle LLM) | le modèle, à chaque tour | élevé | faible par défaut |

La séquence de ce pipeline — récupérer, dédupliquer, filtrer, noter, seuiller,
sélectionner, décider l'angle, rédiger, marquer — est **fixe quel que soit le
contenu**. Faire décider un modèle « et maintenant, quelle étape ? » ajouterait
du coût, de la latence et du non-déterminisme pour zéro bénéfice.

**Les deux seules frontières confiées à un modèle**, parce qu'elles demandent
un vrai jugement :

```
fetch → deduplicate → filter_fresh → filter_unseen → [ score ⟵ LLM ]
   → filter_by_min_score → select_top_k → [ angle ⟵ LLM ] → [ write ⟵ LLM ]
   → mark_seen
```

Dix étapes, dont trois appellent le modèle. Sept sont du code pur, testé,
instantané : sur le run tracé, elles consomment **0,43 seconde sur 3,78**.

*Annexe A3 — `WORKFLOW.md`, grille d'arbitrage complète et décisions de typage.*

---

## 5 — Les garanties

> **Verdict.** Six garanties, chacune adossée à un test qui échoue si elle
> est violée. Ce ne sont pas des intentions : ce sont des conditions de
> livraison.

**Preuve.**

| Garantie | Formulation | Preuve chiffrée |
|---|---|---|
| **Qualité** | Le système ne rédige jamais sur un article hors-sujet | seuil calibré à 8/10 : **100 % de précision**, 0 faux positif sur deux jeux réels (n=30 et n=20) |
| **Budget** | Le coût ne peut pas déraper | plafond dur vérifié entre chaque lot ; dépassement borné à 5 appels, jamais illimité |
| **Robustesse** | Une panne d'API ne casse pas le run | ré-essais bornés avec attente croissante sur 429/529 uniquement ; un article en échec est isolé, le run continue |
| **Idempotence** | Le même article n'est jamais traité deux fois | marquage en dernière étape, après succès ; vérifié sur deux runs consécutifs |
| **Auditabilité** | Chaque run laisse une trace complète | horodatage, durée, coût et issue **par étape, par article et par appel** |
| **Non-régression** | Rien n'est livré sans que tout repasse | **264 tests** automatisés, exécutés avant chaque livraison |

**La latence, mesurée sur le run du 1ᵉʳ septembre :**

| | Valeur |
|---|---|
| Durée totale du run | **3,779 s** |
| Étape de notation (17 articles) | 3,344 s |
| Temps cumulé des 17 appels | 13,383 s |
| **Gain de parallélisation** | **×4,0** |
| Appel le plus lent / médian / le plus rapide | 1,061 s / 0,737 s / 0,667 s |
| Coût propre du moteur d'orchestration | **0,0001 s** |

Treize secondes d'appels compressées en trois : le parallélisme n'est pas une
promesse, c'est un rapport mesuré entre deux horloges.

*Annexes A3 et A4 — `CONCURRENCY.md`, `OBSERVABILITY.md`.*

---

## 6 — Comment les décisions sont prises

> **Verdict.** Sept décisions d'architecture, chacune mesurée avant d'être
> tranchée. L'une d'elles est un refus — et c'est celle dont je suis le plus
> satisfait.

**Preuve.**

| Question posée | Mesure réelle | Décision |
|---|---|---|
| Où placer le seuil de pertinence ? | précision/rappel sur 30 articles annotés à la main + contrôle sur 20 autres | **8/10** — 100 % de précision, 70 % de rappel |
| Le modèle sur-note-t-il hors échantillon ? | 15 articles d'une source jamais vue | accord **0,93**, corrélation de rang **0,87** |
| Faut-il structurer le pipeline en étapes ? | équivalence numérique prouvée, traçabilité gratuite | **Gardé** |
| Deux appels (angle puis rédaction) valent-ils mieux qu'un ? | qualité +0,27/6 sur 10 items — **non significatif** — mais un angle forcé évité, coût ×1,67 | **Gardé, sur l'asymétrie du coût d'erreur** |
| Peut-on paralléliser sans casser l'ordre ? | équivalence sous latences inversées, budget, ré-essais | **Gardé** — gain ×4,0 mesuré |
| Un relecteur automatique améliore-t-il les brouillons ? | détection 100 %, **mais 67 % de faux rejets** (n=14) | **Jeté** |
| Peut-on prouver l'auditabilité et chiffrer le gain ? | trace par appel, latences, gain de parallélisation | **Gardé**, avec la frontière mesure/hypothèse inscrite dans le code |

**Le refus, en détail.** J'ai construit un agent relecteur, écrit 17 tests,
mesuré sur 14 brouillons réels — et les chiffres ont dit non : deux brouillons
corrects sur trois auraient été rejetés à tort. J'en ai aussi diagnostiqué la
cause : ce relecteur ne disposait pas de plus d'information que le rédacteur,
il ne pouvait donc pas mieux juger. Il reste dans le dépôt, testé et
documenté, mais **débranché**.

C'est ce que vous achetez. Pas un agent de plus : une décision, et la
capacité de dire non à son propre travail quand la mesure le contredit.

*Annexe A4 — les sept documents de décision, avec leurs données brutes.*

---

## 7 — Limites assumées

> **Verdict.** Voici ce que ce système ne fait pas. Je préfère vous le dire
> maintenant que vous laisser le découvrir en production.

1. **Rappel de 70 %, choisi.** Sur dix articles vraiment pertinents, trois ne
   sont pas rédigés ce jour-là. Arbitrage assumé : manquer un article coûte
   peu — le flux est quotidien, l'article n'a pas disparu. En publier un
   mauvais coûte votre crédibilité. L'asymétrie tranche en faveur de la
   précision.
2. **Deux runs sur trois n'ont rien produit.** Le contenu réellement
   actionnable est minoritaire dans un flux RSS brut : il a fallu parcourir
   202 articles pour en réunir 10 dignes d'un jeu de test. Le système est un
   filtre exigeant, pas une machine à contenu.
3. **Échantillons petits.** n = 30, 20, 15, 14, 10 selon les mesures. Les
   tendances sont nettes, les intervalles de confiance larges. À revalider à
   plus grand volume.
4. **Brouillons, pas publications.** La sortie est une matière première à
   valider en trente secondes. Le dernier mot reste humain, par conception —
   et ce temps de relecture est déduit du gain annoncé en §2, jamais ignoré.
5. **L'équation de valeur chiffre un temps évité, pas un bénéfice obtenu.**
   Elle ne prouvera jamais que le travail remplacé avait de la valeur.

---

## 8 — Autonomie et exploitation

> **Verdict.** Le système tourne seul, s'archive lui-même, et vous alerte
> quand quelque chose sort de l'ordinaire. Son coût d'exploitation est de
> l'ordre du quart d'euro par mois.

**Preuve.**

| | Valeur |
|---|---|
| Coût moyen par run | **0,0134 $** (3 runs réels) |
| Projection à 21 runs / mois | **≈ 0,28 $**, soit **≈ 0,26 €** |
| Archivage | chaque run horodaté, avec compteurs, coût et brouillons |
| Alerte automatique | déclenchée sur dépassement de coût ou échec d'appel |
| Intervention humaine sur 4 jours | **aucune** |

L'historique est comparable dans le temps : trois runs y sont déjà, et le
quatrième s'y ajoutera au même format.

*Annexe A5 — ordonnancement, commandes de reproduction.*

---

## 9 — Et pour votre cas

> **Verdict.** Ce dossier montre un radar de veille. Ce qui se transpose n'est
> pas le radar : c'est la méthode qui décide quoi construire, et surtout quoi
> ne pas construire.

| Palier | Ce que vous obtenez | Ancré dans |
|---|---|---|
| **Diagnostic d'architecture** | La grille d'arbitrage appliquée à votre cas : quelles étapes restent déterministes, où un agent se justifie, où il ne se justifie pas | §4 |
| **Architecture prête à construire** | Le plan chiffré, les garanties spécifiées, et le protocole de mesure de chaque brique **avant** de l'écrire | §5 et §6 |
| **Construction et remise** | Le système, ses tests, ses documents de décision, sa trace. Vous possédez tout, vous pouvez tout rejouer | §3 et annexes |

La même méthode s'applique au tri de leads entrants, à la qualification de
tickets support, ou à la synthèse de documents réglementaires : même forme —
une séquence fixe, deux ou trois points où il faut juger.

**Prochaine étape.** Trente minutes, en visio : j'applique la grille de §4 à
votre cas et vous repartez avec l'arbitrage, que vous travailliez avec moi ou
non.

---

## Annexes

| # | Contenu | Pour qui |
|---|---|---|
| A1 | `run_report.json`, `run_trace.json`, `docs/run_history.json` — données brutes des trois runs | Qui veut vérifier les chiffres |
| A2 | Les trois brouillons du 30/08 et leurs articles sources | Qui veut juger la sortie |
| A3 | `WORKFLOW.md`, `CONCURRENCY.md`, `MIGRATION.md` — architecture et migration | Architecte |
| A4 | `QUALITY.md`, `HELDOUT.md`, `ANGLE_AGENT.md`, `CRITIC_AGENT.md`, `OBSERVABILITY.md` — les mesures et les décisions | Qui veut auditer la méthode |
| A5 | Commandes de reproduction et ordonnancement | Qui veut rejouer |
| A6 | Stack et dépendances : Python, Pydantic, Claude Haiku 4.5 | Acheteur technique |
