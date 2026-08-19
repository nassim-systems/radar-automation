import pytest

from agent.tools.actions import propose_send_email
from executor.execute import (
    ALREADY_EXECUTED,
    EXECUTED,
    InMemoryExecutionLedger,
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
        execute(proposed, sink=sink, ledger=ledger)  # ProposedAction, non approuvée

    assert sink.performed == []  # rien n'a été exécuté


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
    assert len(sink.performed) == 1  # exécutée une seule fois


def test_approve_requires_human_approver() -> None:
    proposed = propose_send_email(to="a@b.fr", subject="x", body="y", reason="z")

    with pytest.raises(ValueError, match="approbation humaine"):
        approve(proposed, approved_by="   ")
