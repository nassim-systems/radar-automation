from pathlib import Path

import pytest

from agent.tools.actions import propose_send_email
from executor.execute import (
    ALREADY_EXECUTED,
    EXECUTED,
    InMemoryExecutionLedger,
    JsonExecutionLedger,
    NotApproved,
    RecordingActionSink,
    execute,
)
from executor.models import ApprovedAction, approve


def _approved() -> ApprovedAction:
    proposed = propose_send_email(
        to="a@b.fr", subject="Bonjour", body="...", reason="réponse client"
    )
    return approve(proposed, approved_by="alice@pme.fr")


def test_execute_refuses_unapproved_action() -> None:
    proposed = propose_send_email(to="a@b.fr", subject="x", body="y", reason="z")
    sink = RecordingActionSink()
    ledger = InMemoryExecutionLedger()

    with pytest.raises(NotApproved):
        execute(proposed, sink=sink, ledger=ledger)  # ProposedAction, not approved

    assert sink.performed == []  # nothing was executed


def test_execute_accepts_approved_action() -> None:
    sink = RecordingActionSink()
    ledger = InMemoryExecutionLedger()

    result = execute(_approved(), sink=sink, ledger=ledger)

    assert result.status == EXECUTED
    assert len(sink.performed) == 1
    assert sink.performed[0].action == "send_email"


def test_execute_is_idempotent() -> None:
    sink = RecordingActionSink()
    ledger = InMemoryExecutionLedger()
    action = _approved()

    first = execute(action, sink=sink, ledger=ledger)
    second = execute(action, sink=sink, ledger=ledger)

    assert first.status == EXECUTED
    assert second.status == ALREADY_EXECUTED
    assert len(sink.performed) == 1  # executed only once


def test_approve_requires_human_approver() -> None:
    proposed = propose_send_email(to="a@b.fr", subject="x", body="y", reason="z")

    with pytest.raises(ValueError, match="approbation humaine"):
        approve(proposed, approved_by="   ")


def test_json_execution_ledger_persists(tmp_path: Path) -> None:
    path = tmp_path / "executed.json"
    ledger = JsonExecutionLedger(path)

    assert not ledger.was_executed("id-1")
    ledger.mark_executed("id-1")

    # a new instance rereads the file (idempotence across runs)
    assert JsonExecutionLedger(path).was_executed("id-1")
