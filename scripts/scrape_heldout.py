"""Held-out: scrape a fresh RSS feed and run the whole pipeline on it.

Measures the real generalization of the scorer and drafting on never-seen
articles (source different from the annotated set). Outside the test suite:
makes real network and LLM calls, writes the result to ``heldout.json``.

    uv run python scripts/scrape_heldout.py [URL_RSS] [K]
"""
import json
import sys
import urllib.request

from radar.decision.models import ScoredItem
from radar.decision.select_top_k import select_top_k
from radar.drafting.pipeline import drafting_pipeline
from radar.llm.anthropic_client import AnthropicClient
from radar.scoring import score_item
from radar.sources.rss import parse_rss

DEFAULT_URL = "https://www.numerama.com/feed/"
DEFAULT_K = 5
# Honest RSS-client UA: many feeds reject urllib's default UA.
# Does not bypass any anti-bot challenge (those always fail).
USER_AGENT = "Mozilla/5.0 (compatible; radar-automation/0.1; RSS reader)"
DRAFT_MAX_TOKENS = 512  # scoring keeps 16; drafting needs headroom


def main() -> None:
    args = sys.argv[1:]
    url = args[0] if args else DEFAULT_URL
    k = int(args[1]) if len(args) > 1 else DEFAULT_K

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        feed_xml = response.read().decode("utf-8", errors="replace")
    items = parse_rss(feed_xml)
    print(f"{len(items)} articles fetched from {url}")

    scorer_llm = AnthropicClient()
    drafter_llm = AnthropicClient(max_tokens=DRAFT_MAX_TOKENS)
    scored = [
        ScoredItem(item=item, score=score_item(item, scorer_llm).score)
        for item in items
    ]
    top = select_top_k(scored, k)
    drafts = drafting_pipeline(top, drafter_llm)

    payload = [
        {"score": s.score, "title": s.item.title, "draft": d.text}
        for s, d in zip(top, drafts, strict=True)
    ]
    with open("heldout_scrape.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Top {len(top)} + drafts written to heldout_scrape.json:")
    for entry in payload:
        print(f"  [{entry['score']}] {entry['title']}")


if __name__ == "__main__":
    main()
