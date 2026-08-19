from datetime import UTC, datetime

from agent.agent.result import AgentResult
from agent.agent.runner import AgentConfig, handle_message
from agent.conversation.history import conversation_id_for
from agent.conversation.models import Role
from agent.conversation.store import InMemoryConversationStore
from agent.intake.models import InboundMessage, Intent
from agent.tools.base import ProposedAction, ReadResult
from agent.tools.read import CrmReadTool, KnowledgeBaseReadTool
from agent.tools.registry import ReadToolRegistry

RECEIVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


class _AgentFakeLLM:
    """FakeLLM : renvoie un label pour la classification, un texte pour le draft."""

    def __init__(self, *, intent: str, reply: str) -> None:
        self._intent = intent
        self._reply = reply

    def complete(self, prompt: str) -> str:
        if "classifieur" in prompt:  # prompt de classification
            return self._intent
        return self._reply  # prompt de rédaction


class _BoomLLM:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("llm down")


class _SpyReadTool:
    def __init__(self, name: str, data: str) -> None:
        self.name = name
        self.description = f"spy {name}"
        self.data = data
        self.calls: list[str] = []

    def read(self, query: str) -> ReadResult:
        self.calls.append(query)
        return ReadResult(tool=self.name, ok=True, data=self.data)


def _msg(
    body: str, *, sender: str = "client@x.fr", subject: str | None = None
) -> InboundMessage:
    return InboundMessage(
        sender=sender,
        channel="email",
        subject=subject,
        body=body,
        received_at=RECEIVED_AT,
    )


def _config(max_history_turns: int = 10) -> AgentConfig:
    return AgentConfig(max_history_turns=max_history_turns)


def test_handle_message_end_to_end() -> None:
    conversations = InMemoryConversationStore()
    read_tools = ReadToolRegistry(
        [CrmReadTool({"p@x.fr": "Prospect connu"}), KnowledgeBaseReadTool({})]
    )
    llm = _AgentFakeLLM(intent="prospect", reply="Bonjour, voici votre devis.")

    result = handle_message(
        msg=_msg("Je veux un devis", sender="p@x.fr"),
        conversations=conversations,
        read_tools=read_tools,
        llm=llm,
        config=_config(),
    )

    assert isinstance(result, AgentResult)
    assert result.intent == Intent.PROSPECT
    assert result.draft.text == "Bonjour, voici votre devis."
    assert not result.escalated
    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].action == "send_email"
    # le tour client est mémorisé, le fil est identifié
    assert result.conversation_id == conversation_id_for(_msg("x", sender="p@x.fr"))
    turns = conversations.load(result.conversation_id).turns
    assert [t.text for t in turns] == ["Je veux un devis"]


def test_handle_message_executes_no_write() -> None:
    conversations = InMemoryConversationStore()
    llm = _AgentFakeLLM(intent="support", reply="Réponse agent.")

    result = handle_message(
        msg=_msg("Un souci", sender="a@b.fr"),
        conversations=conversations,
        read_tools=ReadToolRegistry([]),
        llm=llm,
        config=_config(),
    )

    # toute écriture n'est qu'une proposition inerte, human-gated
    for action in result.proposed_actions:
        assert isinstance(action, ProposedAction)
        assert action.requires_human_approval is True
        assert not hasattr(action, "execute")

    # rien n'a été "envoyé" : aucun tour AGENT n'est ajouté au fil
    turns = conversations.load(result.conversation_id).turns
    assert all(t.role == Role.CLIENT for t in turns)


def test_handle_message_escalates_on_llm_failure() -> None:
    conversations = InMemoryConversationStore()

    result = handle_message(
        msg=_msg("Bonjour", sender="x@y.fr"),
        conversations=conversations,
        read_tools=ReadToolRegistry([]),
        llm=_BoomLLM(),
        config=_config(),
    )

    assert result.escalated is True
    assert result.intent == Intent.OTHER
    assert result.proposed_actions == []
    # le message reçu est tout de même mémorisé
    assert len(conversations.load(result.conversation_id).turns) == 1


def test_handle_message_routes_read_tools_by_intent() -> None:
    crm = _SpyReadTool("crm_lookup", "client")
    kb = _SpyReadTool("kb_search", "article")
    read_tools = ReadToolRegistry([crm, kb])

    support = handle_message(
        msg=_msg("Aide"),
        conversations=InMemoryConversationStore(),
        read_tools=read_tools,
        llm=_AgentFakeLLM(intent="support", reply="ok"),
        config=_config(),
    )
    assert support.tools_consulted == ["crm_lookup", "kb_search"]
    assert crm.calls and kb.calls

    spam = handle_message(
        msg=_msg("Promo"),
        conversations=InMemoryConversationStore(),
        read_tools=read_tools,
        llm=_AgentFakeLLM(intent="spam", reply="ok"),
        config=_config(),
    )
    assert spam.tools_consulted == []


def test_handle_message_appends_client_turn_only() -> None:
    conversations = InMemoryConversationStore()
    msg = _msg("Première question", sender="a@b.fr")

    handle_message(
        msg=msg,
        conversations=conversations,
        read_tools=ReadToolRegistry([]),
        llm=_AgentFakeLLM(intent="support", reply="Réponse agent"),
        config=_config(),
    )

    cid = conversation_id_for(msg)
    turns = conversations.load(cid).turns
    # politique : seul le tour CLIENT est mémorisé (le brouillon n'est pas envoyé)
    assert len(turns) == 1
    assert turns[0].role == Role.CLIENT
    assert turns[0].text == "Première question"

    # un second message s'ajoute au même fil
    handle_message(
        msg=_msg("Deuxième question", sender="a@b.fr"),
        conversations=conversations,
        read_tools=ReadToolRegistry([]),
        llm=_AgentFakeLLM(intent="support", reply="r2"),
        config=_config(),
    )
    assert [t.text for t in conversations.load(cid).turns] == [
        "Première question",
        "Deuxième question",
    ]
