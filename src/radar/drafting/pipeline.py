from radar.decision.models import ScoredItem
from radar.drafting.parse import Draft, parse_draft
from radar.drafting.prompt import build_draft_prompt
from radar.llm.base import LLMClient


def drafting_pipeline(top_k_items: list[ScoredItem], llm: LLMClient) -> list[Draft]:
    """Generate one draft per top-k item.

    For each item: ``build_draft_prompt → llm.complete → parse_draft``.
    The LLM boundary is isolated behind ``llm`` (FakeLLM in tests, real client
    outside the suite). Deterministic core once ``llm`` is fixed.
    """
    drafts: list[Draft] = []
    for scored in top_k_items:
        prompt = build_draft_prompt(scored.item)
        response = llm.complete(prompt)
        drafts.append(parse_draft(response))
    return drafts
