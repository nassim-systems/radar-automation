"""Scoring concurrent borné, avec budget dur et retry/backoff (module 4.3).

Décisions d'architecture documentées dans ``CONCURRENCY.md`` : valeur par
défaut de ``max_concurrency``, politique de troncature au budget, paramètres
de retry/backoff, périmètre exact des erreurs retentées.
"""
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from core.usage import ListUsageSink
from radar.decision.models import ScoredItem
from radar.domain import RawItem
from radar.llm.base import LLMClient
from radar.llm.errors import TransientLLMError
from radar.scoring import score_item

DEFAULT_MAX_CONCURRENCY = 5


class RetryPolicy(BaseModel):
    """Retry borné, backoff exponentiel plafonné.

    ``max_attempts`` inclut la tentative initiale (3 = 1 essai + 2 retries).
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0


class ConcurrentScoringConfig(BaseModel):
    """Regroupe les paramètres de réglage (même esprit que ``PipelineConfig``
    — évite un ``score_items_concurrently`` à rallonge de paramètres nus)."""

    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_cost_usd: float | None = None
    retry: RetryPolicy = RetryPolicy()


class ConcurrentScoreReport(BaseModel):
    """``scored`` est dans l'ordre d'entrée (parmi les items retenus) —
    l'ordre de complétion réel (variable selon la latence) n'y transparaît
    jamais. ``n_attempted`` compte les items pour lesquels un scoring a été
    *soumis* (retries inclus, budget exclus) ; l'invariant
    ``n_attempted == len(scored) + n_failures`` tient toujours.
    """

    scored: list[ScoredItem]
    n_attempted: int
    n_failures: int
    n_retries: int
    n_skipped_budget: int
    budget_exhausted: bool


def _score_one_with_retry(
    item: RawItem,
    llm: LLMClient,
    policy: RetryPolicy,
    sleep: Callable[[float], None],
) -> tuple[ScoredItem | None, int]:
    """Retourne ``(résultat ou None si échec définitif, nombre de retries)``.

    Seul ``TransientLLMError`` déclenche un retry — jamais une erreur de
    programmation ni une erreur LLM non transitoire (400, auth...), qui
    échoue immédiatement, isolée à cet item (même politique que le
    drafting existant : un échec LLM n'abat pas le lot).
    """
    failures = 0
    retries = 0
    while True:
        try:
            score = score_item(item, llm).score
            return ScoredItem(item=item, score=score), retries
        except TransientLLMError:
            failures += 1
            if failures >= policy.max_attempts:
                return None, retries
            delay = min(
                policy.base_delay_seconds * (2**retries),
                policy.max_delay_seconds,
            )
            sleep(delay)
            retries += 1
        except Exception:
            return None, retries


def score_items_concurrently(  # noqa: PLR0913
    items: list[RawItem],
    llm: LLMClient,
    *,
    config: ConcurrentScoringConfig | None = None,
    usage_sink: ListUsageSink | None = None,
    sleep: Callable[[float], None] = time.sleep,
    wrap_llm: Callable[[RawItem], LLMClient] | None = None,
) -> ConcurrentScoreReport:
    """Score ``items`` en parallèle, borné à ``config.max_concurrency`` appels
    simultanés, réassemblés dans l'ordre d'entrée.

    Traite les items par lots d'au plus ``max_concurrency`` : un lot est
    entièrement soumis et attendu avant de vérifier le budget et de soumettre
    le suivant. Conséquence assumée : un dépassement de budget en cours de
    lot n'interrompt jamais les appels déjà en vol — le dépassement possible
    est borné à un lot (``max_concurrency`` appels), jamais illimité. Cf.
    ``CONCURRENCY.md`` pour la politique complète (troncature, pas d'erreur
    levée).

    ``wrap_llm`` (module 4.6) est un seam d'instrumentation : si fourni, il
    est appelé une fois par item pour obtenir le client à utiliser pour cet
    item — c'est ainsi que la ``CallTimeline`` attribue chaque appel à son
    item sans que ce module connaisse quoi que ce soit à l'observabilité. Le
    défaut (aucun wrapping) laisse le comportement strictement inchangé.
    Six paramètres pour six seams réellement distincts : ``noqa`` assumé,
    comme pour ``build_radar_steps_production`` (module 4.5), plutôt qu'un
    objet de configuration artificiel qui mélangerait réglages et
    dépendances injectées.
    """
    cfg = config if config is not None else ConcurrentScoringConfig()
    if cfg.max_concurrency < 1:
        raise ValueError("max_concurrency doit être >= 1")
    sink = usage_sink if usage_sink is not None else ListUsageSink()

    def wrap(item: RawItem) -> LLMClient:
        return llm if wrap_llm is None else wrap_llm(item)

    indexed = list(enumerate(items))
    ordered: list[tuple[int, ScoredItem]] = []
    n_attempted = 0
    n_failures = 0
    n_retries = 0
    budget_exhausted = False

    with ThreadPoolExecutor(max_workers=cfg.max_concurrency) as executor:
        while indexed:
            if (
                cfg.max_cost_usd is not None
                and sink.total().cost_usd >= cfg.max_cost_usd
            ):
                budget_exhausted = True
                break
            batch = indexed[: cfg.max_concurrency]
            indexed = indexed[cfg.max_concurrency :]
            n_attempted += len(batch)
            futures = {
                executor.submit(
                    _score_one_with_retry, item, wrap(item), cfg.retry, sleep
                ): index
                for index, item in batch
            }
            for future, index in futures.items():
                result, retries = future.result()
                n_retries += retries
                if result is None:
                    n_failures += 1
                else:
                    ordered.append((index, result))

    n_skipped_budget = len(indexed)
    ordered.sort(key=lambda pair: pair[0])
    scored = [result for _, result in ordered]

    return ConcurrentScoreReport(
        scored=scored,
        n_attempted=n_attempted,
        n_failures=n_failures,
        n_retries=n_retries,
        n_skipped_budget=n_skipped_budget,
        budget_exhausted=budget_exhausted,
    )
