from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator


class ReadResult(BaseModel):
    """Résultat d'un outil de lecture — réversible, sans effet de bord."""

    tool: str
    ok: bool
    data: str


class ReadTool(Protocol):
    """Outil de LECTURE seule : réversible, exécutable de façon autonome."""

    name: str
    description: str

    def read(self, query: str) -> ReadResult:
        ...


class ProposedAction(BaseModel):
    """Action d'ÉCRITURE proposée — donnée inerte, jamais exécutable.

    Invariant structurel : ``requires_human_approval`` vaut TOUJOURS ``True``
    (forcé à la validation) et le modèle est gelé (immuable). Il n'existe
    aucune méthode d'exécution : une action ne peut que transiter par la porte
    d'action vers une approbation humaine, hors de ce code.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    params: dict[str, str]
    reason: str
    requires_human_approval: bool = True

    @field_validator("requires_human_approval")
    @classmethod
    def _force_human_approval(cls, value: bool) -> bool:
        # Invariant : impossible de proposer une action sans approbation humaine.
        return True
