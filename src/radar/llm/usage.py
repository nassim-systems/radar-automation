from typing import Protocol

from pydantic import BaseModel


class LlmUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class UsageSink(Protocol):
    """Canal séparé pour l'usage LLM.

    ``AnthropicClient.complete`` continue de renvoyer un ``str`` (aucun des
    nombreux appelants existants — scoring, drafting, agent — n'a besoin de
    changer) ; si un sink est injecté, il est notifié après chaque appel réel.
    """

    def record(self, usage: LlmUsage) -> None: ...


class ListUsageSink:
    """Accumule les usages en mémoire et expose leur somme.

    Même esprit que ``RecordingActionSink`` (module 3.1) : un sink simple pour
    la racine de composition et les tests.
    """

    def __init__(self) -> None:
        self.calls: list[LlmUsage] = []

    def record(self, usage: LlmUsage) -> None:
        self.calls.append(usage)

    def total(self) -> LlmUsage:
        return LlmUsage(
            input_tokens=sum(u.input_tokens for u in self.calls),
            output_tokens=sum(u.output_tokens for u in self.calls),
            cost_usd=sum(u.cost_usd for u in self.calls),
        )
