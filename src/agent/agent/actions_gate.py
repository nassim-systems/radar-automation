from pydantic import BaseModel

from agent.tools.base import ProposedAction

PENDING_HUMAN_APPROVAL = "pending_human_approval"


class GateDecision(BaseModel):
    """Action gate decision: always pending a human."""

    proposed: ProposedAction
    approved: bool
    status: str


def gate_action(proposed: ProposedAction) -> GateDecision:
    """Action gate: the agent can only PROPOSE, never execute.

    Returns an ``approved=False`` decision pending human approval.
    This module deliberately exposes NO execution primitive: no
    ``execute``, no ``run``, no ``dispatch``. Any execution happens
    outside this code, after explicit human approval.
    """
    return GateDecision(
        proposed=proposed,
        approved=False,
        status=PENDING_HUMAN_APPROVAL,
    )
