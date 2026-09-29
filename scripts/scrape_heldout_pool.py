"""Collect a real pool of items from relevant RSS feeds (automation,
no-code, SMB, productivity), to hand-build the module 3.5 held-out
(requested correction: held-out ACTUALLY scraped, not written).

Outside the test suite: real network calls. Writes the raw pool (deduplicated,
unlabeled) to ``scratch_heldout_pool.json`` — human annotation is then done
by hand on that file, outside this script.

    uv run python scripts/scrape_heldout_pool.py
"""
import json
import ssl
import urllib.request
from pathlib import Path
from xml.etree.ElementTree import ParseError

import certifi

from radar.ingest import deduplicate
from radar.sources.rss import parse_rss

USER_AGENT = "Mozilla/5.0 (compatible; radar-automation/0.1; RSS reader)"
OUTPUT_PATH = Path("scratch_heldout_pool.json")

# Feeds manually verified (real network probe) when this script was
# written — see QUALITY.md for the candidates tested and discarded
# (Make.com: no public RSS found; Alsacréations: real RSS but no
# <pubDate>, unsupported by radar.sources.rss.parse_rss).
FEEDS = {
    "zapier_blog": "https://zapier.com/blog/feed/",
    "n8n_blog": "https://blog.n8n.io/rss/",
    "blogdumoderateur_tools": "https://www.blogdumoderateur.com/tools/feed",
    "blogdumoderateur_marketing": "https://www.blogdumoderateur.com/marketing/feed",
    "blogdumoderateur_nocode": "https://www.blogdumoderateur.com/no-code/feed",
    "frenchweb": "https://www.frenchweb.fr/feed",
    "siecledigital": "https://siecledigital.fr/feed/",
}

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20, context=_SSL_CONTEXT) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    pool = []
    for name, url in FEEDS.items():
        try:
            xml = _fetch(url)
            items = parse_rss(xml)
        except (OSError, ParseError) as error:
            print(f"SKIP {name} ({url}) : {type(error).__name__}: {error}")
            continue
        print(f"{name}: {len(items)} items")
        pool.extend(items)

    deduped = deduplicate(pool)
    payload = [item.model_dump(mode="json") for item in deduped]
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nTotal brut : {len(pool)}, after deduplication: {len(deduped)}")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
