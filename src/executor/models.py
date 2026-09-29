import hashlib
import json

from pydantic import BaseModel, ConfigDict, field_validator

from agent.tools.base import ProposedAction


class ApprovedAction(BaseModel):
    """Action approved by a human — the only executable form.

    Frozen (immutable) and carrying an explicit human approver
    (non-empty ``approved_by``, guaranteed by validation). Produced only by
    ``approve``; the ``agent`` package is not allowed to import ``executor``,
    so it can never fabricate one.
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
    # Deterministic content-based identity -> content idempotence.
    payload = json.dumps(
        {"action": action, "params": params, "by": approved_by},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approve(proposed: ProposedAction, *, approved_by: str) -> ApprovedAction:
    """HUMAN approval: turns a ``ProposedAction`` into an ``ApprovedAction``.

    Only factory of ``ApprovedAction``. Requires an explicit human approver.
    """
    if not approved_by.strip():
        raise ValueError("approbation humaine requise : approved_by non vide")
    return ApprovedAction(
        action=proposed.action,
        params=proposed.params,
        approved_by=approved_by,
        action_id=_action_id(proposed.action, proposed.params, approved_by),
    )
