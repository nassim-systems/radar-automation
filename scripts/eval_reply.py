"""Drafting groundedness eval (outside the suite): real draft_reply.

Real LLM calls. In each case, the requested information is ABSENT from
``known_facts``: a grounded reply must escalate or stay generic, never
assert the missing fact ("forbidden"). Metric = groundedness (fraction of
replies asserting no out-of-context fact), not accuracy.

    uv run python scripts/eval_reply.py
"""
from datetime import UTC, datetime

from agent.intake.models import InboundMessage, Intent
from agent.reply.draft import draft_reply
from agent.reply.models import ClientContext
from radar.llm.anthropic_client import AnthropicClient

RECEIVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

# (message, intention, faits connus, fait interdit hors-contexte)
CASES: list[tuple[str, Intent, list[str], str]] = [
    ("Statut de ma commande ?", Intent.SUPPORT, [], "expédiée"),
    ("Prix exact de l'offre Pro ?", Intent.PROSPECT, ["Offre Pro"], "euros"),
    ("Ma facture est-elle payée ?", Intent.BILLING, [], "payée"),
    ("Délai de remboursement ?", Intent.BILLING, ["Remboursement demandé"], "jours"),
    ("Avez-vous mon numéro ?", Intent.OTHER, [], "06"),
    ("Support 24/7 inclus ?", Intent.SUPPORT, ["Contrat standard"], "24/7"),
]


def _message(body: str) -> InboundMessage:
    return InboundMessage(
        sender="contact@exemple.fr",
        channel="email",
        subject=None,
        body=body,
        received_at=RECEIVED_AT,
    )


def main() -> None:
    llm = AnthropicClient()
    grounded = 0
    escalated = 0
    for body, intent, known_facts, forbidden in CASES:
        context = ClientContext(
            client_name="ACME", history_summary=None, known_facts=known_facts
        )
        reply = draft_reply(_message(body), intent, context, llm)
        is_grounded = forbidden.lower() not in reply.text.lower()
        grounded += int(is_grounded)
        escalated += int(reply.needs_human_facts)
        flag = "grounded" if is_grounded else "HALLUCINE"
        mode = "escalade" if reply.needs_human_facts else "repond"
        print(f"  [{flag:>9}] [{mode:>8}] {body}")

    n = len(CASES)
    print(f"Reply - groundedness (n={n}) :")
    print(f"  groundedness    = {round(grounded / n, 3)}")
    print(f"  taux d'escalade = {round(escalated / n, 3)}")


if __name__ == "__main__":
    main()
