"""Jeu de brouillons pour mesurer le CriticAgent (module 4.4).

6 brouillons corrects réutilisés tels quels du run réel du module 4.2
(``draft_strategy_comparison.json`` — déjà jugés bons dans ``ANGLE_AGENT.md``)
+ 8 brouillons **volontairement défectueux**, deux par catégorie demandée
(fait inventé, angle forcé, hors-ligne éditoriale, trop long), construits à
la main pour ce test — pas prétendus réels. Les articles sources restent
réels (titres/résumés issus de ``heldout_representative.json`` et
``production_recall_check.json``, module 3.5) ; seul le brouillon, sur les 8
cas défectueux, est fabriqué délibérément pour être détecté.
"""
from datetime import UTC, datetime

from pydantic import BaseModel

from radar.domain import RawItem
from radar.drafting.parse import Draft

_PUBLISHED_AT = datetime(2026, 8, 20, tzinfo=UTC)


class CriticTestCase(BaseModel):
    id: str
    item: RawItem
    draft: Draft
    expected_accepted: bool
    defect_category: str | None = None  # None si expected_accepted=True


def _item(external_id: str, title: str, summary: str) -> RawItem:
    return RawItem(
        source="heldout_pme_automation",
        external_id=external_id,
        title=title,
        url="",
        published_at=_PUBLISHED_AT,
        summary=summary,
    )


CRITIC_TEST_SET: list[CriticTestCase] = [
    # --- 6 bons brouillons réels (module 4.2, draft_strategy_comparison.json) ---
    CriticTestCase(
        id="good-rozas",
        item=_item(
            "h21",
            "How Rozas uses Zapier to give every lead a 2-minute headstart",
            "As COO of Rozas, Matthew Rozas oversees the systems behind a firm "
            "that receives about 1,800 calls a week on its main line.",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "**Gérer 1 800 appels par semaine sans perdre de temps ?** Chez "
                "Rozas, cabinet d'immigration, le défi était de taille. La "
                "solution : automatiser le premier contact client pour que "
                "chaque demande soit traitée en 2 minutes, sans attendre que "
                "l'équipe d'intake la saisisse manuellement. En éliminant ce "
                "gap critique entre l'appel et l'enregistrement, le cabinet "
                "gagne en réactivité et en efficacité opérationnelle. Un gain "
                "de temps précieux quand chaque lead compte."
            )
        ),
        expected_accepted=True,
    ),
    CriticTestCase(
        id="good-zapier-mcp",
        item=_item(
            "h22",
            "Zapier MCP: Perform tens of thousands of actions in your AI tool",
            "For AI to do something in an app you use, a developer has to "
            "build a complex integration. Or you can fast-track the process "
            "with the Model Context Protocol (MCP).",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "**Automatiser sans développeur : le MCP change la donne pour "
                "les PME**\nJusqu'à présent, faire agir l'IA directement dans "
                "vos outils métier (CRM, comptabilité…) nécessitait "
                "l'intervention d'un développeur. Le Model Context Protocol "
                "(MCP) change la donne : ce protocole agit comme un traducteur "
                "entre vos outils IA et vos applications existantes. Avec le "
                "MCP, les PME peuvent enfin automatiser des tâches répétitives "
                "directement dans leurs logiciels habituels, simplement et "
                "rapidement."
            )
        ),
        expected_accepted=True,
    ),
    CriticTestCase(
        id="good-goose",
        item=_item(
            "h27",
            "Goose",
            "Un logiciel pour exécuter des tâches avec un agent IA local",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Découvrez Goose, un logiciel qui vous permet d'exécuter des "
                "tâches automatisées directement en local grâce à un agent "
                "IA. Fini la dépendance aux API cloud payantes : vous gardez "
                "le contrôle de vos données et maîtrisez vos coûts "
                "d'infrastructure. Une solution idéale pour les PME qui "
                "souhaitent automatiser sans surcharger leur budget "
                "informatique."
            )
        ),
        expected_accepted=True,
    ),
    CriticTestCase(
        id="good-base44",
        item=_item(
            "h28",
            "Base44",
            "Un outil de vibe coding pour créer des applications sans coder",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "**Base44 : créer vos apps métier sans développeur**\nVous "
                "avez une idée d'application pour votre PME mais pas de "
                "ressources dev ? Base44 change la donne en vous permettant "
                "de créer des applications sans coder. Il suffit de décrire "
                "ce que vous voulez, et l'outil se charge du reste. Fini les "
                "délais d'attente et les coûts de développement : prototypez "
                "rapidement vos solutions métier en interne."
            )
        ),
        expected_accepted=True,
    ),
    CriticTestCase(
        id="good-just-eat-spain",
        item=_item(
            "h23",
            "The Zappy Award winner behind Just Eat Spain's faster partner "
            "onboarding",
            "Rubén del Fresno has spent eight years building automation at "
            "Just Eat Spain. His latest system cut time to online from 13 "
            "days to about 5.",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "**Optimiser l'onboarding de vos partenaires : la clé pour "
                "accélérer votre croissance**\nChez Just Eat Spain, une "
                "nouvelle automation a permis de réduire le délai de mise en "
                "ligne des restaurants partenaires de 13 jours à seulement 5 "
                "jours. Comment ? En automatisant les échanges entre les "
                "équipes et en éliminant les tâches manuelles répétitives. "
                "Pour une PME, cela signifie des partenaires opérationnels "
                "plus rapidement et moins de ressources consacrées aux tâches "
                "administratives."
            )
        ),
        expected_accepted=True,
    ),
    CriticTestCase(
        id="good-scraper-studio",
        item=_item(
            "h29",
            "Scraper Studio by Bright Data",
            "Une solution de scraping web avec génération de scrapers par IA",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Découvrez Scraper Studio by Bright Data, une solution de "
                "scraping web pilotée par IA. Grâce à la génération "
                "automatique de scrapers, collectez les données web dont vous "
                "avez besoin sans compétences techniques complexes. Une "
                "solution pensée pour simplifier l'accès aux données pour les "
                "PME, que ce soit pour la veille concurrentielle ou la "
                "prospection commerciale."
            )
        ),
        expected_accepted=True,
    ),
    # --- fait inventé (2) ---
    CriticTestCase(
        id="defect-invented-fact-goose",
        item=_item(
            "h27",
            "Goose",
            "Un logiciel pour exécuter des tâches avec un agent IA local",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Découvrez Goose, un logiciel qui vous permet d'exécuter des "
                "tâches automatisées directement en local grâce à un agent "
                "IA. Selon une étude interne, 68 % des PME utilisatrices ont "
                "réduit leurs coûts cloud de moitié dès le premier mois. Fini "
                "la dépendance aux API cloud payantes : vous gardez le "
                "contrôle de vos données."
            )
        ),
        expected_accepted=False,
        defect_category="fait_invente",
    ),
    CriticTestCase(
        id="defect-invented-fact-base44",
        item=_item(
            "h28",
            "Base44",
            "Un outil de vibe coding pour créer des applications sans coder",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "**Base44 : créer vos apps métier sans développeur**\nDéjà "
                "adopté par plus de 50 000 PME en France selon son fondateur, "
                "Base44 change la donne en vous permettant de créer des "
                "applications sans coder. Il suffit de décrire ce que vous "
                "voulez, et l'outil se charge du reste."
            )
        ),
        expected_accepted=False,
        defect_category="fait_invente",
    ),
    # --- angle forcé (2) ---
    CriticTestCase(
        id="defect-forced-angle-bedrock",
        item=_item(
            "h24",
            "Build multi-agent teams that remember every customer with "
            "Amazon Bedrock AgentCore",
            "A triage agent routes each customer question to one of three "
            "specialists. All four run on a single Amazon Bedrock AgentCore "
            "harness and share one memory per customer.",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Imaginez des agents IA spécialisés qui travaillent ensemble "
                "pour vos clients, sans jamais leur demander de répéter leurs "
                "questions. Avec Amazon Bedrock AgentCore, créez des équipes "
                "d'agents intelligents qui partagent une mémoire commune par "
                "client. Résultat : une expérience client plus fluide et "
                "efficace, même pour les PME."
            )
        ),
        expected_accepted=False,
        defect_category="angle_force",
    ),
    CriticTestCase(
        id="defect-forced-angle-rhine-group",
        item=_item(
            "prod-recall-rhine-group",
            "RHINE GROUP : Mario Draghi et Patrick Collison veulent "
            "construire la coalition qui manque à l'Europe",
            "Mario Draghi et Patrick Collison lancent Rhine Group, une "
            "organisation indépendante réunissant économistes, entrepreneurs "
            "et investisseurs pour renforcer la coalition économique "
            "européenne.",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Mario Draghi et Patrick Collison lancent Rhine Group pour "
                "renforcer la coalition économique européenne. Une initiative "
                "qui pourrait, à terme, ouvrir de nouvelles opportunités de "
                "financement et de soutien pour les PME innovantes en quête "
                "de croissance à l'échelle européenne."
            )
        ),
        expected_accepted=False,
        defect_category="angle_force",
    ),
    # --- hors ligne éditoriale (2) ---
    CriticTestCase(
        id="defect-off-brand-hype-spam",
        item=_item(
            "h27",
            "Goose",
            "Un logiciel pour exécuter des tâches avec un agent IA local",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "🚀🚀🚀 INCROYABLE !!! Cet outil va TOUT CHANGER pour votre "
                "business !!! 😱🔥 Ne ratez surtout pas cette pépite absolue, "
                "foncez tester MAINTENANT avant tout le monde !!! "
                "#automatisation #IA #business #PME #entrepreneur #startup"
            )
        ),
        expected_accepted=False,
        defect_category="hors_ligne_editoriale",
    ),
    CriticTestCase(
        id="defect-off-brand-english",
        item=_item(
            "h28",
            "Base44",
            "Un outil de vibe coding pour créer des applications sans coder",
        ),
        draft=Draft(
            text=(
                "# Draft post\n"
                "Check out this amazing tool that will change how your small "
                "business builds software forever! You won't believe how "
                "much time and money you'll save with Base44."
            )
        ),
        expected_accepted=False,
        defect_category="hors_ligne_editoriale",
    ),
    # --- trop long (2) ---
    CriticTestCase(
        id="defect-too-long-goose",
        item=_item(
            "h27",
            "Goose",
            "Un logiciel pour exécuter des tâches avec un agent IA local",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Découvrez Goose, un logiciel qui vous permet d'exécuter des "
                "tâches automatisées directement en local grâce à un agent "
                "IA. Fini la dépendance aux API cloud payantes. Vous gardez "
                "le contrôle de vos données. Vous maîtrisez vos coûts "
                "d'infrastructure. C'est une solution particulièrement "
                "adaptée aux petites structures. Elle ne nécessite aucune "
                "compétence technique avancée. L'installation est simple et "
                "rapide. Le support communautaire est actif. De nombreux "
                "tutoriels sont disponibles en ligne. Une solution idéale "
                "pour les PME qui souhaitent automatiser sans surcharger leur "
                "budget informatique."
            )
        ),
        expected_accepted=False,
        defect_category="trop_long",
    ),
    CriticTestCase(
        id="defect-too-long-zapier-mcp",
        item=_item(
            "h22",
            "Zapier MCP: Perform tens of thousands of actions in your AI tool",
            "For AI to do something in an app you use, a developer has to "
            "build a complex integration. Or you can fast-track the process "
            "with the Model Context Protocol (MCP).",
        ),
        draft=Draft(
            text=(
                "# Brouillon de post\n"
                "Le Model Context Protocol change la donne pour les PME qui "
                "veulent automatiser sans développeur. Il agit comme un "
                "traducteur entre l'IA et vos outils métier. Cela concerne le "
                "CRM, la comptabilité, et bien d'autres logiciels. "
                "Auparavant, il fallait un développeur pour construire des "
                "intégrations complexes. Désormais, l'IA peut agir "
                "directement dans vos applications. Cela représente un gain "
                "de temps considérable pour les petites structures. De plus, "
                "cela réduit les coûts liés au développement sur mesure. Les "
                "PME peuvent ainsi rester compétitives face aux grandes "
                "entreprises. C'est une avancée majeure pour la "
                "démocratisation de l'automatisation."
            )
        ),
        expected_accepted=False,
        defect_category="trop_long",
    ),
]
