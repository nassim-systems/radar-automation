from agent.intake.models import Intent
from agent.reply.models import ESCALATION_MARKER, DraftReply


def parse_reply(raw: str) -> DraftReply:
    """Structure la sortie du LLM en ``DraftReply`` (fonction pure).

    Extrait le texte, retire le marqueur d'escalade et positionne
    ``needs_human_facts=True`` si le modèle a escaladé — ou, défaut sûr, si la
    réponse est vide. ``intent`` est neutre ici (fixé par ``draft_reply``).
    """
    text = raw.strip()
    escalated = ESCALATION_MARKER in text
    cleaned = text.replace(ESCALATION_MARKER, "").strip()
    return DraftReply(
        text=cleaned,
        intent=Intent.OTHER,
        needs_human_facts=escalated or not cleaned,
    )
