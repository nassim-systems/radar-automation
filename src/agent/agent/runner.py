from collections.abc import Iterable

from pydantic import BaseModel

from agent.agent.result import AgentResult
from agent.conversation.history import build_history_block, conversation_id_for
from agent.conversation.models import Role, Turn
from agent.conversation.store import ConversationStore
from agent.intake.classify import classify
from agent.intake.models import InboundMessage, Intent
from agent.reply.draft import draft_reply
from agent.reply.models import ClientContext, DraftReply
from agent.tools.actions import propose_send_email
from agent.tools.base import ProposedAction
from agent.tools.registry import ReadToolRegistry
from radar.llm.base import LLMClient


class AgentConfig(BaseModel):
    max_history_turns: int


# Structured routing of READ tools by intent: hard-coded, deterministic,
# no ReAct loop. Such fixed routing is auditable and reproducible.
_ROUTES: dict[Intent, tuple[str, ...]] = {
    Intent.PROSPECT: ("crm_lookup",),
    Intent.SUPPORT: ("crm_lookup", "kb_search"),
    Intent.BILLING: ("crm_lookup",),
    Intent.SPAM: (),
    Intent.OTHER: (),
}


def handle_message(
    *,
    msg: InboundMessage,
    conversations: ConversationStore,
    read_tools: ReadToolRegistry,
    llm: LLMClient,
    config: AgentConfig,
) -> AgentResult:
    """Deterministic agent loop, pure over its injected dependencies.

    Chains: ``classify`` → ``load conversation`` → ``build_history_block`` →
    structured routing of read-tools by intent → grounded ``draft_reply`` →
    ``ProposedAction`` (human-gated) for sending → append of the CLIENT turn.

    - **No external write** is executed: every write is a
      ``ProposedAction`` (``requires_human_approval=True``).
    - **Safe default**: any LLM failure (classification) escalates.
    - **Does not re-sanitize** the ``<turn>`` block: it is already safe.
    - **Append policy**: only the CLIENT turn (the received message) is
      stored. The agent draft is NOT added, because it is not sent until a
      human approves the ``ProposedAction`` — history must reflect only what
      actually happened.
    """
    conversation_id = conversation_id_for(msg)
    conversation = conversations.load(conversation_id)
    history = build_history_block(conversation.turns, config.max_history_turns)

    try:
        intent = classify(msg, llm)
    except Exception:
        # Safe-default : impossible de comprendre -> escalade humaine.
        _record_client_turn(conversations, conversation_id, msg)
        return _escalation(conversation_id, Intent.OTHER, tools_consulted=[])

    facts, consulted = _consult_read_tools(read_tools, msg, _ROUTES.get(intent, ()))
    context = ClientContext(
        client_name=None,
        history_summary=history or None,
        known_facts=facts,
    )
    draft = draft_reply(msg=msg, intent=intent, context=context, llm=llm)
    proposed = _propose_reply(msg, intent, draft)

    _record_client_turn(conversations, conversation_id, msg)
    return AgentResult(
        intent=intent,
        draft=draft,
        proposed_actions=proposed,
        conversation_id=conversation_id,
        tools_consulted=consulted,
        escalated=draft.needs_human_facts,
    )


def _consult_read_tools(
    read_tools: ReadToolRegistry, msg: InboundMessage, tool_names: Iterable[str]
) -> tuple[list[str], list[str]]:
    facts: list[str] = []
    consulted: list[str] = []
    for name in tool_names:
        consulted.append(name)
        result = read_tools.read(name, _query_for(msg, name))
        if result.ok:
            facts.append(result.data)
    return facts, consulted


def _query_for(msg: InboundMessage, tool_name: str) -> str:
    if tool_name == "crm_lookup":
        return msg.sender
    return msg.subject or msg.body


def _propose_reply(
    msg: InboundMessage, intent: Intent, draft: DraftReply
) -> list[ProposedAction]:
    if not draft.text:
        return []
    subject = f"Re: {msg.subject}" if msg.subject else "Votre message"
    return [
        propose_send_email(
            to=msg.sender,
            subject=subject,
            body=draft.text,
            reason=f"Reply '{intent.value}' requires approval before sending.",
        )
    ]


def _record_client_turn(
    conversations: ConversationStore, conversation_id: str, msg: InboundMessage
) -> None:
    conversations.append(
        conversation_id,
        Turn(role=Role.CLIENT, text=msg.body, at=msg.received_at),
    )


def _escalation(
    conversation_id: str, intent: Intent, tools_consulted: list[str]
) -> AgentResult:
    return AgentResult(
        intent=intent,
        draft=DraftReply(text="", intent=intent, needs_human_facts=True),
        proposed_actions=[],
        conversation_id=conversation_id,
        tools_consulted=tools_consulted,
        escalated=True,
    )
