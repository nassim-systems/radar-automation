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


class TeeUsageSink:
    """Diffuse chaque usage à plusieurs sinks, dans l'ordre donné.

    Nécessaire depuis le module 4.6 (``OBSERVABILITY.md``) : le budget dur du
    scoring concurrent lit le total agrégé d'un ``ListUsageSink`` (module 4.3)
    tandis que la timeline d'appels attribue le même usage à l'appel LLM en
    cours. Deux consommateurs, une seule source — plutôt que deux comptages
    parallèles qui pourraient diverger.

    Aucune politique propre : ni filtrage, ni transformation, ni absorption
    d'erreur. Si un sink lève, l'erreur se propage (un sink cassé est un bug,
    pas un incident à avaler).
    """

    def __init__(self, sinks: list[UsageSink]) -> None:
        self._sinks = sinks

    def record(self, usage: LlmUsage) -> None:
        for sink in self._sinks:
            sink.record(usage)
