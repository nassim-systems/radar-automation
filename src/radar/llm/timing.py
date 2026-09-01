"""Instrumentation temporelle des appels LLM (module 4.6).

Décorateur ``LLMClient`` — pas une modification d'``AnthropicClient``. La
raison est la même que pour le ``UsageSink`` du module 3.4 : le client réel
n'a pas à connaître l'observabilité, et un décorateur laisse les ``FakeLLM``/
``ScriptedLLM`` des tests instrumentables de la même façon que le client de
production, sans code conditionnel.

**Attribution par item.** Le décorateur porte le *sujet* de l'appel (l'item
en cours) et sa *phase* (le nom de l'étape). L'attribution est donc explicite
au point d'appel, pas devinée après coup : chaque étape crée un décorateur
par item. C'est le pendant, côté appels, de la trace par étape du module 4.1.

**Attribution de l'usage (tokens/coût).** ``CallTimeline`` implémente aussi
``UsageSink`` : branchée via ``TeeUsageSink`` à côté du ``ListUsageSink``
existant, elle reçoit l'usage réel du même appel et l'attache à l'appel en
cours. La corrélation passe par une variable *thread-local* et c'est
volontairement correct : ``AnthropicClient.complete`` notifie son sink de
façon synchrone, dans le thread qui exécute l'appel — le même que celui du
décorateur, y compris dans le ``ThreadPoolExecutor`` du scoring concurrent
(module 4.3). Aucun comptage de tokens/coût n'est réinventé ici : la source
reste l'usage renvoyé par le SDK.
"""
import threading
import time
from datetime import UTC, datetime

from pydantic import BaseModel

from core.usage import LlmUsage
from radar.llm.base import LLMClient


class CallSubject(BaseModel):
    """Ce sur quoi porte un appel LLM — un item du flux, en pratique."""

    key: str
    title: str
    url: str | None = None


class LlmCallRecord(BaseModel):
    """Un appel LLM réellement émis : quand, combien de temps, sur quoi,
    avec quelle issue et quel usage.

    Un *retry* (module 4.3) produit un enregistrement par tentative — c'est
    le nombre d'appels réellement émis à l'API qui est tracé, pas le nombre
    d'items traités. ``PipelineReport.n_llm_calls`` doit donc coïncider avec
    ``len(calls)`` : la divergence des deux compteurs serait un bug, et les
    avoir mesurés indépendamment permet de le voir.
    """

    phase: str
    subject: CallSubject | None = None
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    ok: bool
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class _InFlight:
    """Emplacement mutable de l'appel en cours dans le thread courant.

    Volontairement hors Pydantic : c'est un détail de mécanique interne,
    jamais sérialisé, jamais exposé.
    """

    __slots__ = ("usage",)

    def __init__(self) -> None:
        self.usage: LlmUsage | None = None


class CallTimeline:
    """Journal des appels LLM d'un run, sûr en environnement concurrent.

    Implémente ``UsageSink`` (méthode ``record``) pour recevoir l'usage réel
    de l'appel en cours — cf. le docstring du module pour la correction de
    l'attribution thread par thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._local = threading.local()
        self.calls: list[LlmCallRecord] = []

    def record(self, usage: LlmUsage) -> None:
        """``UsageSink`` : attache l'usage à l'appel en cours dans CE thread.

        Un usage reçu hors de tout appel instrumenté est ignoré plutôt
        qu'attribué au hasard à un autre appel : mieux vaut un champ absent
        qu'un chiffre faux.
        """
        in_flight: _InFlight | None = getattr(self._local, "in_flight", None)
        if in_flight is not None:
            in_flight.usage = usage

    def begin_call(self) -> _InFlight:
        in_flight = _InFlight()
        self._local.in_flight = in_flight
        return in_flight

    def end_call(self, call: LlmCallRecord) -> None:
        self._local.in_flight = None
        with self._lock:
            self.calls.append(call)

    def clear(self) -> None:
        with self._lock:
            self.calls.clear()

    def snapshot(self) -> list[LlmCallRecord]:
        """Copie triée par instant de début — l'ordre d'insertion reflète
        l'ordre de *fin* des appels, qui n'a pas de sens en concurrence."""
        with self._lock:
            return sorted(self.calls, key=lambda call: call.started_at)


class TimedLLMClient:
    """Décore un ``LLMClient`` : chronomètre chaque appel et l'enregistre.

    Transparent pour l'appelant — ``complete`` renvoie le même ``str`` et
    laisse passer les exceptions inchangées (une erreur LLM reste une erreur
    LLM ; le module 4.3 s'appuie sur le type exact pour décider d'un retry).
    Un appel qui échoue est tracé lui aussi, avec ``ok=False`` : c'est
    précisément le cas où l'on veut savoir combien de temps il a coûté.
    """

    def __init__(
        self,
        inner: LLMClient,
        timeline: CallTimeline,
        *,
        phase: str,
        subject: CallSubject | None = None,
    ) -> None:
        self._inner = inner
        self._timeline = timeline
        self._phase = phase
        self._subject = subject

    def complete(self, prompt: str) -> str:
        in_flight = self._timeline.begin_call()
        started_at = datetime.now(tz=UTC)
        started = time.monotonic()
        error: str | None = None
        try:
            return self._inner.complete(prompt)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            usage = in_flight.usage
            self._timeline.end_call(
                LlmCallRecord(
                    phase=self._phase,
                    subject=self._subject,
                    started_at=started_at,
                    ended_at=datetime.now(tz=UTC),
                    duration_seconds=time.monotonic() - started,
                    ok=error is None,
                    error=error,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    cost_usd=usage.cost_usd if usage else None,
                )
            )
