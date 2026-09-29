from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator


class ReadResult(BaseModel):
    """Result of a read tool — reversible, no side effect."""

    tool: str
    ok: bool
    data: str


class ReadTool(Protocol):
    """READ-only tool: reversible, can run autonomously."""

    name: str
    description: str

    def read(self, query: str) -> ReadResult:
        ...


class ProposedAction(BaseModel):
    """Proposed WRITE action — inert data, never executable.

    Structural invariant: ``requires_human_approval`` is ALWAYS ``True``
    (forced at validation) and the model is frozen (immutable). There is
    no execution method: an action can only pass through the action gate
    to a human approval, outside this code.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    params: dict[str, str]
    reason: str
    requires_human_approval: bool = True

    @field_validator("requires_human_approval")
    @classmethod
    def _force_human_approval(cls, value: bool) -> bool:
        # Invariant: an action cannot be proposed without human approval.
        return True
