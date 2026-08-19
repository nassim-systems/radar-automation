import hashlib
import json

from pydantic import BaseModel, ConfigDict, field_validator

from agent.tools.base import ProposedAction


class ApprovedAction(BaseModel):
    """Action approuvée par un humain — la seule forme exécutable.

    Gelée (immuable) et porteuse d'un approbateur humain explicite
    (``approved_by`` non vide, garanti par validation). Produite uniquement par
    ``approve`` ; le package ``agent`` n'a pas le droit d'importer ``executor``,
    il ne peut donc jamais en fabriquer une.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    params: dict[str, str]
    approved_by: str
    action_id: str

    @field_validator("approved_by")
    @classmethod
    def _require_human(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("approbation humaine requise : approved_by non vide")
        return value


class ExecutionResult(BaseModel):
    action_id: str
    status: str
    detail: str


def _action_id(action: str, params: dict[str, str], approved_by: str) -> str:
    # Identité déterministe fondée sur le contenu -> idempotence par contenu.
    payload = json.dumps(
        {"action": action, "params": params, "by": approved_by},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approve(proposed: ProposedAction, *, approved_by: str) -> ApprovedAction:
    """Approbation HUMAINE : transforme une ``ProposedAction`` en ``ApprovedAction``.

    Seule fabrique d'``ApprovedAction``. Exige un approbateur humain explicite.
    """
    if not approved_by.strip():
        raise ValueError("approbation humaine requise : approved_by non vide")
    return ApprovedAction(
        action=proposed.action,
        params=proposed.params,
        approved_by=approved_by,
        action_id=_action_id(proposed.action, proposed.params, approved_by),
    )
