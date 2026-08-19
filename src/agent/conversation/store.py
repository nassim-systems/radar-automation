from typing import Protocol

from agent.conversation.models import Conversation, Turn


class ConversationStore(Protocol):
    def load(self, conversation_id: str) -> Conversation:
        ...

    def append(self, conversation_id: str, turn: Turn) -> Conversation:
        ...


class InMemoryConversationStore:
    """Store non persistant : état d'instance uniquement, aucun global mutable.

    ``load`` renvoie toujours une copie indépendante (muter le résultat
    n'altère pas le store).
    """

    def __init__(self) -> None:
        self._turns_by_id: dict[str, list[Turn]] = {}

    def load(self, conversation_id: str) -> Conversation:
        turns = self._turns_by_id.get(conversation_id, [])
        return Conversation(conversation_id=conversation_id, turns=list(turns))

    def append(self, conversation_id: str, turn: Turn) -> Conversation:
        turns = self._turns_by_id.setdefault(conversation_id, [])
        turns.append(turn)
        return Conversation(conversation_id=conversation_id, turns=list(turns))
