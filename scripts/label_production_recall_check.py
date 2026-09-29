"""Build the "real recall" check set (module 3.5, point 4).

The exact batch of the 20 items from the real run of 3.3 was not kept (the
pipeline only persists aggregate counters, not the list of fetched items —
see ``PipelineReport``). Closest honest substitute: the 20 **most recent,
unselected** items from the same real pool as the held-out
(``scrape_heldout_pool.json``), hence an unbiased sample (no curation
toward a label tier) representative of what a real run would produce
today with the enriched feeds.

    uv run python scripts/scrape_heldout_pool.py   # (if needed) regenerate pool
    uv run python scripts/label_production_recall_check.py
"""
import json
from pathlib import Path

POOL_PATH = Path("scratch_heldout_pool.json")
HELDOUT_PATH = Path("src/radar/eval/heldout_representative.json")
OUTPUT_PATH = Path("src/radar/eval/production_recall_check.json")
N = 20

# url -> human label (0-10), assigned from the real title + summary,
# before any scorer run.
LABELS: dict[str, int] = {
    "https://www.frenchweb.fr/pasqal-au-nasdaq-le-quantique-francais-cherche-le-capital-de-son-industrialisation/463104": 0,
    "https://www.frenchweb.fr/pourquoi-dotai-dotjs-est-le-seul-evenement-tech-incontournable-de-la-rentree/463091": 2,
    "https://siecledigital.fr/2026/08/27/trois-francais-viennent-de-vendre-leur-entreprise-a-nvidia-pour-pres-de-13-milliards-de-dollars/": 0,
    "https://siecledigital.fr/2026/08/27/google-repond-deja-par-ia-a-plus-dune-recherche-sur-deux-en-france/": 3,
    "https://siecledigital.fr/2026/08/27/vous-utilisez-chatgpt-5-reglages-a-modifier-obligatoirement-pour-proteger-votre-vie-privee/": 3,
    "https://blog.n8n.io/rbac-for-ai-agents/": 4,
    "https://blog.n8n.io/etl-pipeline/": 4,
    "https://siecledigital.fr/2026/08/27/la-russie-a-utilise-chatgpt-pour-alimenter-une-campagne-de-desinformation/": 0,
    "https://siecledigital.fr/2026/08/27/grok-depasse-par-ses-rivaux-elon-musk-veut-mettre-les-bouchees-doubles/": 1,
    "https://siecledigital.fr/2026/08/27/facturation-electronique-face-aux-craintes-de-piratage-le-gouvernement-veut-rassurer/": 6,
    "https://www.frenchweb.fr/hugging-face-la-plateforme-que-tous-les-geants-de-lia-ont-interet-a-acheter-mais-a-quel-prix/463073": 1,
    "https://www.frenchweb.fr/ipo-dopenai-et-danthropic-le-jour-ou-lintelligence-artificielle-devra-montrer-ses-comptes/463002": 0,
    "https://zapier.com/blog/what-is-hubspot": 6,
    "https://zapier.com/blog/migrate-from-dropbox-to-google-drive": 4,
    "https://zapier.com/blog/add-zoom-to-google-calendar-as-default": 3,
    "https://zapier.com/blog/google-ai-mode": 3,
    "https://www.frenchweb.fr/rhine-group-mario-draghi-et-patrick-collison-veulent-construire-la-coalition-qui-manque-a-leurope/463066": 0,
    "https://siecledigital.fr/2026/08/26/instagram-lance-un-outil-qui-monte-automatiquement-vos-reels-en-quelques-secondes/": 6,
    "https://www.frenchweb.fr/defense-leurope-veut-des-champions-paneuropeens-chaque-etat-veut-le-sien/463007": 0,
    "https://www.frenchweb.fr/arcspace-leve-plus-de-2-millions-deuros-pour-faire-passer-les-satellites-du-jetable-au-reparable/463048": 0,
}


def main() -> None:
    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    heldout_urls = {
        item["url"]
        for item in json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))
    }
    by_url = {item["url"]: item for item in pool}

    missing = [url for url in LABELS if url not in by_url]
    if missing:
        raise SystemExit(f"URLs not found in the pool: {missing}")
    overlap = set(LABELS) & heldout_urls
    if overlap:
        raise SystemExit(f"overlaps the calibration held-out: {overlap}")
    if len(LABELS) != N:
        raise SystemExit(f"attendu {N} items, obtenu {len(LABELS)}")

    labeled = []
    for i, (url, label) in enumerate(LABELS.items()):
        item = dict(by_url[url])
        item["source"] = "production_recall_check"
        item["external_id"] = f"p{i:02d}"
        item["label"] = label
        labeled.append(item)

    OUTPUT_PATH.write_text(
        json.dumps(labeled, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(labeled)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
