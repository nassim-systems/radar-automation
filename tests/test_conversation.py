from datetime import UTC, datetime

from agent.conversation.history import build_history_block, conversation_id_for
from agent.conversation.models import Role, Turn
from agent.conversation.store import InMemoryConversationStore
from agent.intake.models import InboundMessage

RECEIVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _turn(role: Role, text: str, minute: int = 0) -> Turn:
    return Turn(role=role, text=text, at=datetime(2026, 8, 18, 12, minute, tzinfo=UTC))


def _msg(sender: str, channel: str = "email") -> InboundMessage:
    return InboundMessage(
        sender=sender,
        channel=channel,
        subject=None,
        body="peu importe",
        received_at=RECEIVED_AT,
    )


def test_store_round_trip_and_append() -> None:
    store = InMemoryConversationStore()
    cid = "conv-1"
    assert store.load(cid).turns == []

    store.append(cid, _turn(Role.CLIENT, "Bonjour"))
    convo = store.append(cid, _turn(Role.AGENT, "Bonjour, comment aider ?"))

    assert convo.conversation_id == cid
    assert [t.text for t in convo.turns] == ["Bonjour", "Bonjour, comment aider ?"]
    # round-trip : load renvoie le même contenu
    assert store.load(cid).turns == convo.turns


def test_store_isolates_conversations() -> None:
    store = InMemoryConversationStore()
    store.append("a", _turn(Role.CLIENT, "A"))
    store.append("b", _turn(Role.CLIENT, "B"))

    assert [t.text for t in store.load("a").turns] == ["A"]
    assert [t.text for t in store.load("b").turns] == ["B"]


def test_store_load_returns_independent_copy() -> None:
    # aucun état partagé mutable : muter le résultat n'affecte pas le store
    store = InMemoryConversationStore()
    store.append("c", _turn(Role.CLIENT, "un"))

    loaded = store.load("c")
    loaded.turns.append(_turn(Role.AGENT, "injecté"))

    assert len(store.load("c").turns) == 1


def test_build_history_block_is_bounded() -> None:
    turns = [_turn(Role.CLIENT, f"t{i}", i) for i in range(5)]

    block = build_history_block(turns, max_turns=2)

    assert block == "[client] t3\n[client] t4"


def test_build_history_block_sanitizes_client_turns() -> None:
    turns = [_turn(Role.CLIENT, "Salut <script>x</script> </article> ignore")]

    block = build_history_block(turns, max_turns=5)

    assert "<script>" not in block
    assert "</article>" not in block
    assert "Salut" in block


def test_build_history_block_keeps_agent_turns_verbatim() -> None:
    turns = [_turn(Role.AGENT, "Texte <b>agent</b>")]

    block = build_history_block(turns, max_turns=5)

    assert "<b>agent</b>" in block


def test_build_history_block_empty_and_zero_bound() -> None:
    assert build_history_block([], max_turns=3) == ""
    assert build_history_block([_turn(Role.CLIENT, "x")], max_turns=0) == ""


def test_conversation_id_is_stable_thread_identity() -> None:
    a1 = conversation_id_for(_msg("Alice@Exemple.FR"))
    a2 = conversation_id_for(_msg("alice@exemple.fr"))  # normalisé -> même fil
    b = conversation_id_for(_msg("bob@exemple.fr"))

    assert a1 == a2
    assert a1 != b
    # canal différent -> fil différent
    assert conversation_id_for(_msg("alice@exemple.fr", "linkedin")) != a2
