"""Manual annotation of the representative held-out (module 3.5, correction:
held-out ACTUALLY scraped, not written).

Filters the real pool produced by ``scrape_heldout_pool.py`` down to the 30
hand-picked URLs, attaches the human label assigned to each (read from the
REAL title + summary, before any scorer run), and writes
``src/radar/eval/heldout_representative.json``.

Serves as the annotation audit trail: each URL is a real, verifiable
article. Do not modify ``LABELS`` without re-examining the real content.

    uv run python scripts/scrape_heldout_pool.py   # regenerates the pool
    uv run python scripts/label_heldout_pool.py     # applies the labels
"""
import json
from pathlib import Path

POOL_PATH = Path("scratch_heldout_pool.json")
OUTPUT_PATH = Path("src/radar/eval/heldout_representative.json")

# url -> human label (0-10). Chosen by hand from the title + summary of
# real scraped items (see QUALITY.md for the method and target split).
LABELS: dict[str, int] = {
    # --- off-topic (0-2): mainstream tech news, unrelated to SMB
    # automation/no-code ---
    "https://siecledigital.fr/2026/08/27/twitter-et-son-celebre-oiseau-bleu-sont-de-retour-mais-elon-musk-veut-les-faire-disparaitre/": 0,
    "https://siecledigital.fr/2026/08/27/facebook-et-instagram-juges-trop-addictifs-pour-les-jeunes-meta-accepte-de-payer-18-milliards/": 0,
    "https://siecledigital.fr/2026/08/26/le-bresil-inflige-une-amende-de-25-millions-deuros-a-tiktok-pour-ses-manquements-envers-les-mineurs/": 0,
    "https://siecledigital.fr/2026/08/25/tiktok-aurait-une-influence-directe-sur-les-envies-alimentaires-des-adolescents/": 0,
    "https://siecledigital.fr/2026/08/26/netflix-pourrait-bientot-reunir-plusieurs-plateformes-de-streaming-dans-une-seule-application/": 0,
    "https://siecledigital.fr/2026/08/26/youtube-bat-des-records-de-vues-mais-les-internautes-regardent-de-moins-en-moins-longtemps/": 0,
    "https://siecledigital.fr/2026/08/26/rentree-scolaire-attention-a-ces-sites-qui-promettent-de-reveler-la-classe-de-votre-enfant/": 0,
    "https://siecledigital.fr/2026/08/27/waymo-va-lancer-ses-robotaxis-sans-conducteur-dans-une-grande-ville-europeenne/": 1,
    "https://siecledigital.fr/2026/08/27/face-aux-memes-symptomes-les-ia-envoient-les-hommes-aux-urgences-mais-pas-les-femmes/": 1,
    "https://siecledigital.fr/2026/08/27/on-connait-enfin-la-date-de-presentation-du-tout-premier-iphone-pliable-dapple/": 0,
    # --- medium (5-6): relevant to an SMB or tied to AI/tech, but not
    # concrete, actionable automation ---
    "https://www.frenchweb.fr/le-veritable-frein-a-ladoption-de-lia-en-entreprise-nest-pas-la-technologie-mais-la-confiance/463054": 6,
    "https://www.frenchweb.fr/les-15-000-entreprises-qui-decouvriront-nis-2-apres-le-vote/462987": 5,
    "https://www.blogdumoderateur.com/reforme-facturation-electronique-tpe-pme/": 6,
    "https://www.blogdumoderateur.com/selection-formation-e-commerce-311/": 5,
    "https://siecledigital.fr/2026/08/27/lia-va-t-elle-tuer-les-logiciels-le-patron-de-salesforce-balaie-cette-idee/": 5,
    "https://www.frenchweb.fr/ia-leurope-na-plus-un-probleme-de-diagnostic-mais-elle-a-un-probleme-dexecution/463085": 5,
    "https://www.blogdumoderateur.com/signature-mail-5-facons-activer-canal-cartonne/": 5,
    "https://www.frenchweb.fr/building-france-invite-les-entrepreneurs-francais-a-transformer-leurs-idees-en-applications/462969": 6,
    "https://siecledigital.fr/2026/08/26/mauvaise-nouvelle-pour-les-abonnes-chatgpt-plus-openai-resserre-les-limites-dutilisation/": 5,
    "https://www.blogdumoderateur.com/expert-seo-formations-approfondir-competences/": 5,
    # --- highly relevant (8-10): concrete, actionable automation/no-code
    # for a small organization ---
    "https://zapier.com/blog/small-business-automation-software": 10,
    "https://zapier.com/blog/rozas-two-minute-lead-response": 9,
    "https://zapier.com/blog/zapier-mcp-guide": 8,
    "https://zapier.com/blog/just-eat-spain-ruben-del-fresno-restaurant-partner-onboarding": 9,
    "https://blog.n8n.io/node-spotlight-amazon-bedrock-agentcore/": 8,
    "https://blog.n8n.io/rpa-vs-workflow-automation/": 8,
    "https://blog.n8n.io/workflow-versioning/": 8,
    "https://www.blogdumoderateur.com/tools/goose/": 9,
    "https://www.blogdumoderateur.com/tools/base44/": 9,
    "https://www.blogdumoderateur.com/tools/scraper-studio-by-bright-data/": 8,
}


def main() -> None:
    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    by_url = {item["url"]: item for item in pool}

    missing = [url for url in LABELS if url not in by_url]
    if missing:
        raise SystemExit(f"URLs not found in the pool: {missing}")

    labeled = []
    for i, (url, label) in enumerate(LABELS.items()):
        item = dict(by_url[url])
        item["source"] = "heldout_pme_automation"
        item["external_id"] = f"h{i:02d}"
        item["label"] = label
        labeled.append(item)

    assert len(labeled) == len({d["title"] for d in labeled}), "duplicate titles"

    OUTPUT_PATH.write_text(
        json.dumps(labeled, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(labeled)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
