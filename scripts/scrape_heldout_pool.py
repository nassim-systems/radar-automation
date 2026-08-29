"""Collecte un pool réel d'items depuis des flux RSS pertinents (automation,
no-code, PME, productivité), pour construire à la main le held-out du module
3.5 (correction demandée : held-out RÉELLEMENT scrapé, pas rédigé).

Hors suite de tests : vrais appels réseau. Écrit le pool brut (dédupliqué,
non labellisé) dans ``scratch_heldout_pool.json`` — l'annotation humaine se
fait ensuite à la main sur ce fichier, hors de ce script.

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

# Flux vérifiés manuellement (probe réseau réel) au moment de l'écriture de ce
# script — cf. QUALITY.md pour le détail des candidats testés et écartés
# (Make.com : pas de RSS public trouvé ; Alsacréations : RSS réel mais sans
# <pubDate>, non supporté par radar.sources.rss.parse_rss).
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
    print(f"\nTotal brut : {len(pool)}, après dédoublonnage : {len(deduped)}")
    print(f"Écrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
