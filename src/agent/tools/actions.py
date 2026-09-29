from agent.tools.base import ProposedAction


def propose_send_email(
    *, to: str, subject: str, body: str, reason: str
) -> ProposedAction:
    """Build a PROPOSAL to send an email — never sent."""
    return ProposedAction(
        action="send_email",
        params={"to": to, "subject": subject, "body": body},
        reason=reason,
    )


def propose_create_ticket(
    *, subject: str, body: str, reason: str
) -> ProposedAction:
    """Build a PROPOSAL to create a ticket — never created."""
    return ProposedAction(
        action="create_ticket",
        params={"subject": subject, "body": body},
        reason=reason,
    )


def propose_issue_refund(
    *, invoice: str, amount: str, reason: str
) -> ProposedAction:
    """Build a PROPOSAL for a refund — never executed."""
    return ProposedAction(
        action="issue_refund",
        params={"invoice": invoice, "amount": amount},
        reason=reason,
    )
