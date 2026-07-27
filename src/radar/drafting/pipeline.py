from radar.decision.models import ScoredItem
from radar.drafting.parse import Draft, parse_draft
from radar.drafting.prompt import build_draft_prompt
from radar.llm.base import LLMClient


def drafting_pipeline(top_k_items: list[ScoredItem], llm: LLMClient) -> list[Draft]:
    """Génère un brouillon par item du top-k.

    Pour chaque item : ``build_draft_prompt → llm.complete → parse_draft``.
    La frontière LLM est isolée derrière ``llm`` (FakeLLM en test, vrai client
    hors suite). Cœur déterministe à ``llm`` fixé.
    """
    drafts: list[Draft] = []
    for scored in top_k_items:
        prompt = build_draft_prompt(scored.item)
        response = llm.complete(prompt)
        drafts.append(parse_draft(response))
    return drafts
