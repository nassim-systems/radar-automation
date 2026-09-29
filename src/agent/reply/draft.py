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
    """Draft a grounded reply (read-only, no send, no action).

    LLM boundary isolated behind ``llm`` (injected). Safe default = escalation:
    only the ``llm.complete`` call is isolated and, if it fails, we return an
    escalation (``needs_human_facts=True``) rather than an invented reply.
    The real ``intent`` (the one from intake) is carried onto the result.
    """
    prompt = build_reply_prompt(msg, intent, context)
    try:
        raw = llm.complete(prompt)
    except Exception:
        return DraftReply(text="", intent=intent, needs_human_facts=True)
    return parse_reply(raw).model_copy(update={"intent": intent})
