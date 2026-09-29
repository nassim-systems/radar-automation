"""Bounded concurrent scoring, with hard budget and retry/backoff (module 4.3).

Architecture decisions documented in ``CONCURRENCY.md``: default value of
``max_concurrency``, budget truncation policy, retry/backoff parameters,
exact scope of retried errors.
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
    """Bounded retry, capped exponential backoff.

    ``max_attempts`` includes the initial attempt (3 = 1 try + 2 retries).
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0


class ConcurrentScoringConfig(BaseModel):
    """Groups the tuning parameters (same spirit as ``PipelineConfig``
    — avoids a ``score_items_concurrently`` with a long list of bare params)."""

    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_cost_usd: float | None = None
    retry: RetryPolicy = RetryPolicy()


class ConcurrentScoreReport(BaseModel):
    """``scored`` is in input order (among the retained items) — the actual
    completion order (varying with latency) never shows through.
    ``n_attempted`` counts the items for which a scoring was *submitted*
    (retries included, budget-skipped excluded); the invariant
    ``n_attempted == len(scored) + n_failures`` always holds.
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
    """Return ``(result or None on final failure, number of retries)``.

    Only ``TransientLLMError`` triggers a retry — never a programming error
    nor a non-transient LLM error (400, auth...), which fails immediately,
    isolated to that item (same policy as the existing drafting: an LLM
    failure does not take down the batch).
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
    """Score ``items`` in parallel, bounded to ``config.max_concurrency``
    simultaneous calls, reassembled in input order.

    Processes items in batches of at most ``max_concurrency``: a batch is
    fully submitted and awaited before checking the budget and submitting
    the next. Accepted consequence: a budget overrun mid-batch never
    interrupts calls already in flight — the possible overrun is bounded
    to one batch (``max_concurrency`` calls), never unbounded. See
    ``CONCURRENCY.md`` for the full policy (truncation, no error
    raised).

    ``wrap_llm`` (module 4.6) is an instrumentation seam: if provided, it
    is called once per item to obtain the client to use for that item —
    this is how the ``CallTimeline`` attributes each call to its item
    without this module knowing anything about observability. The default
    (no wrapping) leaves behavior strictly unchanged.
    Six parameters for six genuinely distinct seams: ``noqa`` accepted,
    as for ``build_radar_steps_production`` (module 4.5), rather than an
    artificial config object that would mix settings and injected
    dependencies.
    """
    cfg = config if config is not None else ConcurrentScoringConfig()
    if cfg.max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")
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
