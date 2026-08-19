from agent.intake.models import Intent


def parse_classification(raw: str) -> Intent:
    """Parse la réponse du LLM en ``Intent`` (Enum fermé).

    Fonction pure. La casse et les espaces de bord sont ignorés. Tout label
    inconnu, vide ou ambigu retombe sur ``Intent.OTHER`` — le défaut sûr.
    """
    normalized = raw.strip().lower()
    for intent in Intent:
        if intent.value == normalized:
            return intent
    return Intent.OTHER
