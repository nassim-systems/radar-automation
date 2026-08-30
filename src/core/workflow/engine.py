import time
from typing import Protocol

from core.usage import ListUsageSink, LlmUsage
from core.workflow.models import StepTrace, WorkflowRun, WorkflowState


class Step(Protocol):
    name: str

    def run(self, state: WorkflowState) -> WorkflowState: ...


class WorkflowError(Exception):
    """Levée quand une étape échoue — porte la trace partielle et l'usage
    déjà accumulé, pour que l'échec reste observable (pas seulement signalé).

    N'est jamais utilisée pour avaler une erreur : ``run_workflow`` la lève
    systématiquement via ``raise ... from error``, l'exception d'origine
    reste visible dans la chaîne. Cohérent avec la politique déjà en place
    dans ``radar/pipeline.py`` : un bug de code se propage — ici, au niveau
    de l'étape entière plutôt que de l'item.
    """

    def __init__(
        self,
        *,
        step_name: str,
        trace: list[StepTrace],
        usage: LlmUsage,
        original: Exception,
    ) -> None:
        self.step_name = step_name
        self.trace = trace
        self.usage = usage
        self.original = original
        super().__init__(f"étape « {step_name} » a échoué : {original}")


def run_workflow(
    steps: list[Step],
    initial: WorkflowState,
    *,
    usage_sink: ListUsageSink | None = None,
) -> WorkflowRun:
    """Enchaîne ``steps`` en état-passant : chaque étape reçoit l'état
    renvoyé par la précédente et en renvoie un nouveau (immuable).

    - **Abort, pas skip** : si une étape lève, l'exécution s'arrête et
      ``WorkflowError`` est levée (trace partielle + usage déjà accumulé
      attachés). Une étape est une unité de travail complète (fetch, score,
      draft...) — la « sauter » silencieusement casserait les étapes
      suivantes qui dépendent de son résultat. La résilience fine (item par
      item, ex. un échec LLM isolé) reste la responsabilité de chaque étape,
      pas de l'orchestrateur — cf. ``WORKFLOW.md``.
    - **Observabilité réutilisée, pas réinventée** : ``usage_sink`` est le
      ``ListUsageSink`` du module 3.4, injecté dans les clients LLM que les
      étapes utilisent en interne. ``run_workflow`` ne fait qu'en lire le
      total agrégé ; il ne sait rien des tokens/coûts. Seule la durée par
      étape est mesurée ici, une préoccupation que le sink d'usage ne couvre
      pas.
    """
    sink = usage_sink if usage_sink is not None else ListUsageSink()
    state = initial
    trace: list[StepTrace] = []
    for step in steps:
        started = time.monotonic()
        try:
            state = step.run(state)
        except Exception as error:
            trace.append(
                StepTrace(
                    name=step.name,
                    duration_seconds=time.monotonic() - started,
                    ok=False,
                    error=str(error),
                )
            )
            raise WorkflowError(
                step_name=step.name,
                trace=trace,
                usage=sink.total(),
                original=error,
            ) from error
        trace.append(
            StepTrace(
                name=step.name,
                duration_seconds=time.monotonic() - started,
                ok=True,
            )
        )
    return WorkflowRun(final_state=state, trace=trace, usage=sink.total())
