import json
from pathlib import Path
from typing import Protocol

from executor.models import ApprovedAction, ExecutionResult

EXECUTED = "executed"
ALREADY_EXECUTED = "already_executed"


class NotApproved(Exception):
    """Levée quand ``execute`` reçoit autre chose qu'une ``ApprovedAction``."""


class ActionSink(Protocol):
    """Capacité d'agir réellement (ex. futur client SMTP). Injectée."""

    def perform(self, action: ApprovedAction) -> None:
        ...


class ExecutionLedger(Protocol):
    """Journal des actions déjà exécutées (support de l'idempotence)."""

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
    """Journal persistant des actions exécutées — idempotence entre les runs.

    Même esprit que ``JsonSeenStore`` : lecture résiliente (fichier absent ou
    corrompu → aucune action connue) plutôt que de lever.
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
    """Sink de démonstration : enregistre l'action au lieu d'agir sur le monde."""

    def __init__(self) -> None:
        self.performed: list[ApprovedAction] = []

    def perform(self, action: ApprovedAction) -> None:
        self.performed.append(action)


def execute(
    action: ApprovedAction, *, sink: ActionSink, ledger: ExecutionLedger
) -> ExecutionResult:
    """Seule primitive d'exécution réelle (package ``executor``).

    Fail-closed : refuse tout ce qui n'est pas une ``ApprovedAction`` porteuse
    d'une approbation humaine. Idempotente : une action déjà exécutée (même
    ``action_id``) n'est pas rejouée. La frontière d'import garantit que le
    package ``agent`` ne peut jamais atteindre cette fonction.
    """
    if not isinstance(action, ApprovedAction) or not action.approved_by.strip():
        raise NotApproved(
            "execute n'accepte qu'une ApprovedAction approuvée par un humain"
        )
    if ledger.was_executed(action.action_id):
        return ExecutionResult(
            action_id=action.action_id,
            status=ALREADY_EXECUTED,
            detail="déjà exécutée (idempotence)",
        )
    sink.perform(action)
    ledger.mark_executed(action.action_id)
    return ExecutionResult(
        action_id=action.action_id, status=EXECUTED, detail=action.action
    )
