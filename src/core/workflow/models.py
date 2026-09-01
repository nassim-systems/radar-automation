from datetime import datetime

from pydantic import BaseModel, ConfigDict

from core.usage import LlmUsage


class WorkflowState(BaseModel):
    """État de base d'un workflow.

    ``frozen=True`` rend l'immuabilité structurelle, pas seulement
    conventionnelle : une étape ne peut pas muter l'état reçu (une tentative
    lève ``pydantic.ValidationError``), elle doit renvoyer une nouvelle
    instance (``state.model_copy(update={...})``). Chaque workflow concret
    définit sa propre sous-classe avec ses champs métier typés — cf.
    ``WORKFLOW.md`` (décision « typage de WorkflowState »).
    """

    model_config = ConfigDict(frozen=True)


class StepTrace(BaseModel):
    """Trace d'exécution d'une étape : nom, horodatage, durée, issue.

    ``started_at``/``ended_at`` sont des instants UTC (horloge murale) : ils
    situent l'étape dans le temps réel et permettent de la corréler aux
    appels LLM qu'elle a déclenchés. ``duration_seconds`` reste mesurée
    séparément avec ``time.monotonic()``, insensible aux ajustements
    d'horloge. Les deux ne sont donc pas redondants — c'est volontaire :
    l'un sert à situer, l'autre à mesurer.
    """

    name: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    ok: bool
    error: str | None = None


class WorkflowRun(BaseModel):
    """Résultat d'un ``run_workflow`` réussi : état final, trace, usage agrégé.

    ``usage`` réutilise ``LlmUsage``/``UsageSink`` du module 3.4 (tokens,
    coût) — aucune observabilité parallèle réinventée ici. La durée par
    étape (``StepTrace.duration_seconds``), elle, est une préoccupation
    d'orchestration que le sink d'usage LLM ne couvre pas ; elle est mesurée
    directement par ``run_workflow``.

    ``duration_seconds`` (module 4.6) est la latence **de bout en bout** du
    run — pas la somme des étapes : l'écart entre les deux est le coût
    d'orchestration lui-même, et il doit rester visible plutôt qu'être
    dissous dans une somme.
    """

    final_state: WorkflowState
    trace: list[StepTrace]
    usage: LlmUsage
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
