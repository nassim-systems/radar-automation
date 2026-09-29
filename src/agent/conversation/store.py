import json
from pathlib import Path
from typing import Protocol

from agent.conversation.models import Conversation, Turn

_RawTurn = dict[str, object]
_RawStore = dict[str, list[_RawTurn]]


class ConversationStore(Protocol):
    def load(self, conversation_id: str) -> Conversation:
        ...

    def append(self, conversation_id: str, turn: Turn) -> Conversation:
        ...


class InMemoryConversationStore:
    """Non-persistent store: instance state only, no mutable global.

    ``load`` always returns an independent copy (mutating the result does
    not alter the store). Convenient for tests.
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


class JsonConversationStore:
    """Persistent JSON-file store — memory survives across runs.

    Same spirit as ``JsonSeenStore`` (Phase 1): resilient read (missing or
    corrupt file → empty conversation) rather than raising.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, conversation_id: str) -> Conversation:
        raw = self._read().get(conversation_id, [])
        turns = [Turn.model_validate(item) for item in raw]
        return Conversation(conversation_id=conversation_id, turns=turns)

    def append(self, conversation_id: str, turn: Turn) -> Conversation:
        data = self._read()
        raw = data.get(conversation_id, [])
        raw.append(turn.model_dump(mode="json"))
        data[conversation_id] = raw
        self._write(data)
        turns = [Turn.model_validate(item) for item in raw]
        return Conversation(conversation_id=conversation_id, turns=turns)

    def _read(self) -> _RawStore:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: _RawStore) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self.path.write_text(content, encoding="utf-8")
