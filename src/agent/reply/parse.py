from agent.intake.models import Intent
from agent.reply.models import ESCALATION_MARKER, DraftReply


def parse_reply(raw: str) -> DraftReply:
    """Structure the LLM output into a ``DraftReply`` (pure function).

    Extracts the text, strips the escalation marker and sets
    ``needs_human_facts=True`` if the model escalated — or, as a safe default,
    if the reply is empty. ``intent`` is neutral here (set by ``draft_reply``).
    """
    text = raw.strip()
    escalated = ESCALATION_MARKER in text
    cleaned = text.replace(ESCALATION_MARKER, "").strip()
    return DraftReply(
        text=cleaned,
        intent=Intent.OTHER,
        needs_human_facts=escalated or not cleaned,
    )
