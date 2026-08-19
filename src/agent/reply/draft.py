from agent.intake.models import InboundMessage, Intent
from agent.reply.models import ClientContext, DraftReply
from agent.reply.parse import parse_reply
from agent.reply.prompt import build_reply_prompt
from radar.llm.base import LLMClient


def draft_reply(
    msg: InboundMessage,
    intent: Intent,
    context: ClientContext,
    llm: LLMClient,
) -> DraftReply:
    """Rédige une réponse ancrée (lecture seule, aucun envoi, aucune action).

    Frontière LLM isolée derrière ``llm`` (injecté). Défaut sûr = escalade :
    seul l'appel ``llm.complete`` est isolé et, s'il échoue, on renvoie une
    escalade (``needs_human_facts=True``) plutôt qu'une réponse inventée.
    L'``intent`` réel (celui de l'intake) est reporté sur le résultat.
    """
    prompt = build_reply_prompt(msg, intent, context)
    try:
        raw = llm.complete(prompt)
    except Exception:
        return DraftReply(text="", intent=intent, needs_human_facts=True)
    return parse_reply(raw).model_copy(update={"intent": intent})
