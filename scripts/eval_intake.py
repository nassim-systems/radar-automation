"""Categorical intake eval (outside the suite): real classify vs human labels.

Real LLM calls. Small hand-annotated set; computes accuracy and the
confusion matrix (categorical metric, not ordinal).

    uv run python scripts/eval_intake.py
"""
from collections import Counter
from datetime import UTC, datetime

from agent.intake.classify import classify
from agent.intake.models import InboundMessage, Intent
from radar.llm.anthropic_client import AnthropicClient

RECEIVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

CASES: list[tuple[str, Intent]] = [
    ("Je voudrais un devis pour équiper mon équipe", Intent.PROSPECT),
    ("Intéressé par une démo de votre produit", Intent.PROSPECT),
    ("L'application plante à chaque connexion", Intent.SUPPORT),
    ("Comment réinitialiser mon mot de passe ?", Intent.SUPPORT),
    ("Un prélèvement en double sur ma facture", Intent.BILLING),
    ("Je veux résilier mon abonnement et être remboursé", Intent.BILLING),
    ("GAGNEZ 5000 euros, cliquez ici maintenant !!!", Intent.SPAM),
    ("Backlinks pas chers pour booster votre SEO", Intent.SPAM),
    ("Merci beaucoup, très bonne journée à vous", Intent.OTHER),
    ("Joyeuses fêtes à toute l'équipe", Intent.OTHER),
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
    pairs = [(expected, classify(_message(body), llm)) for body, expected in CASES]

    accuracy = sum(1 for true, pred in pairs if true == pred) / len(pairs)
    confusion = Counter((true.value, pred.value) for true, pred in pairs)

    print(f"Intake — categorical eval (n={len(pairs)})")
    print(f"  accuracy = {round(accuracy, 3)}")
    print("  confusion (human label -> prediction):")
    for (true, pred), count in sorted(confusion.items()):
        print(f"    {true:>9} -> {pred:<9} : {count}")


if __name__ == "__main__":
    main()
