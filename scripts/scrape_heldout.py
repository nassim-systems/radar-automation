"""Held-out : scrape un flux RSS frais et exécute tout le pipeline dessus.

Mesure la vraie généralisation du scorer et du drafting sur des articles
jamais vus (source différente du jeu annoté). Hors suite de tests : effectue
de vrais appels réseau et LLM, écrit le résultat dans ``heldout.json``.

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


def main() -> None:
    args = sys.argv[1:]
    url = args[0] if args else DEFAULT_URL
    k = int(args[1]) if len(args) > 1 else DEFAULT_K

    with urllib.request.urlopen(url) as response:
        feed_xml = response.read().decode("utf-8", errors="replace")
    items = parse_rss(feed_xml)
    print(f"{len(items)} articles récupérés depuis {url}")

    llm = AnthropicClient()
    scored = [
        ScoredItem(item=item, score=score_item(item, llm).score) for item in items
    ]
    top = select_top_k(scored, k)
    drafts = drafting_pipeline(top, llm)

    payload = [
        {"score": s.score, "title": s.item.title, "draft": d.text}
        for s, d in zip(top, drafts, strict=True)
    ]
    with open("heldout.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Top {len(top)} + brouillons écrits dans heldout.json :")
    for entry in payload:
        print(f"  [{entry['score']}] {entry['title']}")


if __name__ == "__main__":
    main()
