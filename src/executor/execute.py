import json
from pathlib import Path
from typing import Protocol

from executor.models import ApprovedAction, ExecutionResult

EXECUTED = "executed"
ALREADY_EXECUTED = "already_executed"


class NotApproved(Exception):
    """Raised when ``execute`` receives anything other than an ``ApprovedAction``."""


class ActionSink(Protocol):
    """Ability to really act (e.g. a future SMTP client). Injected."""

    def perform(self, action: ApprovedAction) -> None:
        ...


class ExecutionLedger(Protocol):
    """Journal of already executed actions (idempotence support)."""

    def was_executed(self, action_id: str) -> bool:
        ...

    def mark_executed(self, action_id: str) -> None:
        ...


class InMemoryExecutionLedger:
    def __init__(self) -> None:
        self._done: set[str] = set()

    def was_executed(self, action_id: str) -> bool:
        return action_id in self._done

    def mark_executed(self, action_id: str) -> None:
        self._done.add(action_id)


class JsonExecutionLedger:
    """Persistent journal of executed actions — idempotence across runs.

    Same spirit as ``JsonSeenStore``: resilient read (missing or corrupt
    file → no known action) rather than raising.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def was_executed(self, action_id: str) -> bool:
        return action_id in self._read()

    def mark_executed(self, action_id: str) -> None:
        done = self._read()
        done.add(action_id)
        self.path.write_text(
            json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8"
        )

    def _read(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        return set(data) if isinstance(data, list) else set()


class RecordingActionSink:
    """Demo sink: records the action instead of acting on the world."""

    def __init__(self) -> None:
        self.performed: list[ApprovedAction] = []

    def perform(self, action: ApprovedAction) -> None:
        self.performed.append(action)


def execute(
    action: ApprovedAction, *, sink: ActionSink, ledger: ExecutionLedger
) -> ExecutionResult:
    """The only real execution primitive (``executor`` package).

    Fail-closed: refuses anything that is not an ``ApprovedAction`` carrying
    a human approval. Idempotent: an already executed action (same
    ``action_id``) is not replayed. The import boundary guarantees that the
    ``agent`` package can never reach this function.
    """
    if not isinstance(action, ApprovedAction) or not action.approved_by.strip():
        raise NotApproved(
            "execute only accepts an ApprovedAction approved by a human"
        )
    if ledger.was_executed(action.action_id):
        return ExecutionResult(
            action_id=action.action_id,
            status=ALREADY_EXECUTED,
            detail="already executed (idempotent)",
        )
    sink.perform(action)
    ledger.mark_executed(action.action_id)
    return ExecutionResult(
        action_id=action.action_id, status=EXECUTED, detail=action.action
    )
