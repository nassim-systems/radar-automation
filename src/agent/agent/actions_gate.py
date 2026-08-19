from pydantic import BaseModel

from agent.tools.base import ProposedAction

PENDING_HUMAN_APPROVAL = "pending_human_approval"


class GateDecision(BaseModel):
    """Décision de la porte d'action : toujours en attente d'un humain."""

    proposed: ProposedAction
    approved: bool
    status: str


def gate_action(proposed: ProposedAction) -> GateDecision:
    """Porte d'action : l'agent ne peut que PROPOSER, jamais exécuter.

    Renvoie une décision ``approved=False`` en attente d'approbation humaine.
    Ce module n'expose volontairement AUCUNE primitive d'exécution : ni
    ``execute``, ni ``run``, ni ``dispatch``. L'exécution éventuelle a lieu
    hors de ce code, après validation humaine explicite.
    """
    return GateDecision(
        proposed=proposed,
        approved=False,
        status=PENDING_HUMAN_APPROVAL,
    )
