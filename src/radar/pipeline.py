from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel

from radar.decision.models import ScoredItem
from radar.decision.select_top_k import select_top_k
from radar.domain import RawItem
from radar.drafting.parse import Draft, parse_draft
from radar.drafting.prompt import build_draft_prompt
from radar.ingest import deduplicate, filter_fresh, filter_unseen, item_key
from radar.llm.base import LLMClient
from radar.scoring import score_item
from radar.tools.seen_store import SeenStore


class PipelineConfig(BaseModel):
    now: datetime
    max_age: timedelta
    k: int
    max_scored: int


class ScoredDraft(BaseModel):
    """Un brouillon apparié à son item et à son score (pas de liste positionnelle)."""

    item: RawItem
    score: int
    draft: Draft


class PipelineReport(BaseModel):
    n_fetched: int
    n_dedup: int
    n_fresh: int
    n_unseen: int
    n_scored: int
    n_drafted: int
    n_llm_calls: int
    n_failures: int
    drafts: list[ScoredDraft]


def run_pipeline(
    *,
    fetch_items: Callable[[], list[RawItem]],
    seen_store: SeenStore,
    llm: LLMClient,
    config: PipelineConfig,
) -> PipelineReport:
    """Exécute le pipeline complet avec dépendances injectées.

    Étages : ``fetch → dedup → fresh → unseen → score → select_top_k → draft``.

    - **Budget LLM** : au plus ``config.max_scored`` items sont scorés.
    - **Idempotence** : les items scorés sont marqués vus dans ``seen_store``,
      donc un second run ne les re-drafte pas (les items non scorés pour cause
      de budget restent « à voir »).
    - **Isolation des échecs** : un draft qui lève est compté dans
      ``n_failures`` sans interrompre le run.
    - **Appariement** : chaque brouillon est un ``ScoredDraft`` (item + score).
    """
    fetched = fetch_items()
    deduped = deduplicate(fetched)
    fresh_items = filter_fresh(deduped, now=config.now, max_age=config.max_age)
    unseen_items = filter_unseen(fresh_items, seen_store.load_seen())

    n_llm_calls = 0
    scored: list[ScoredItem] = []
    for item in unseen_items[: config.max_scored]:
        n_llm_calls += 1
        scored.append(ScoredItem(item=item, score=score_item(item, llm).score))

    top = select_top_k(scored, config.k)

    drafts: list[ScoredDraft] = []
    n_failures = 0
    for entry in top:
        try:
            prompt = build_draft_prompt(entry.item)
            n_llm_calls += 1
            draft = parse_draft(llm.complete(prompt))
        except Exception:
            n_failures += 1
            continue
        drafts.append(ScoredDraft(item=entry.item, score=entry.score, draft=draft))

    seen_store.add_seen(item_key(entry.item) for entry in scored)

    return PipelineReport(
        n_fetched=len(fetched),
        n_dedup=len(deduped),
        n_fresh=len(fresh_items),
        n_unseen=len(unseen_items),
        n_scored=len(scored),
        n_drafted=len(drafts),
        n_llm_calls=n_llm_calls,
        n_failures=n_failures,
        drafts=drafts,
    )
