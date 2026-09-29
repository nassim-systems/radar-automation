import json
from pathlib import Path
from typing import Protocol

from radar.observability.models import RunRecord

_DEFAULT_MAX_RECORDS = 500


class RunHistoryStore(Protocol):
    def append(self, record: RunRecord) -> None: ...

    def recent(self, n: int) -> list[RunRecord]: ...


class InMemoryRunHistoryStore:
    """Non-persistent store (tests, ephemeral runs)."""

    def __init__(self, max_records: int = _DEFAULT_MAX_RECORDS) -> None:
        self._max_records = max_records
        self._records: list[RunRecord] = []

    def append(self, record: RunRecord) -> None:
        self._records.append(record)
        self._records = self._records[-self._max_records :]

    def recent(self, n: int) -> list[RunRecord]:
        return list(self._records[-n:]) if n > 0 else []


class JsonRunHistoryStore:
    """Append-only persistent JSON-file store, bounded to ``max_records``.

    Same resilient read as ``JsonSeenStore``/``JsonConversationStore``
    (missing or corrupt file → empty history rather than raising).
    Unlike ``JsonConversationStore`` (one key per conversation, hence
    naturally bounded), a run history grows without end — so only the
    ``max_records`` most recent entries are kept on each
    write.
    """

    def __init__(self, path: Path, max_records: int = _DEFAULT_MAX_RECORDS) -> None:
        self.path = path
        self._max_records = max_records

    def append(self, record: RunRecord) -> None:
        records = self._read()
        records.append(record.model_dump(mode="json"))
        records = records[-self._max_records :]
        self.path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def recent(self, n: int) -> list[RunRecord]:
        if n <= 0:
            return []
        raw = self._read()
        return [RunRecord.model_validate(item) for item in raw[-n:]]

    def _read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []
