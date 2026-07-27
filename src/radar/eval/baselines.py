from radar.domain import RawItem

CONSTANT_SCORE = 5
KEYWORD_WEIGHT = 3
MAX_SCORE = 10

# Mots-clés « automatisation-PME » pour la baseline naïve.
KEYWORDS = (
    "automatis",
    "no-code",
    "no code",
    "nocode",
    "workflow",
    "zapier",
    "make.com",
    "rpa",
    "agent",
    "chatbot",
    "crm",
    "facturation",
    "devis",
    "intelligence artificielle",
    "assistant ia",
    "gagner du temps",
    "productivité",
    "outil",
    "logiciel",
    "saas",
    "tpe",
    "pme",
)


def constant_scorer(item: RawItem) -> int:
    """Baseline triviale : renvoie toujours le même score neutre."""
    return CONSTANT_SCORE


def keyword_scorer(item: RawItem) -> int:
    """Baseline naïve : score fonction du nombre de mots-clés PME présents."""
    text = f"{item.title} {item.summary or ''}".lower()
    hits = sum(1 for keyword in KEYWORDS if keyword in text)
    return min(MAX_SCORE, hits * KEYWORD_WEIGHT)
