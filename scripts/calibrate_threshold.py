"""Calibration de ``min_score`` : precision/recall du held-out représentatif
à plusieurs seuils.

Hors suite de tests : vrais appels LLM. Charge le held-out scellé
(``src/radar/eval/heldout_representative.json``), le score avec le vrai
modèle, calcule precision_at_threshold/recall_at_threshold pour chaque seuil
de ``THRESHOLDS``, écrit ``quality_calibration.json``. Les résultats de ce
script alimentent ``QUALITY.md`` (module 3.5).

    uv run python scripts/calibrate_threshold.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.eval import harness
from radar.eval.metrics import precision_at_threshold, recall_at_threshold
from radar.llm.anthropic_client import AnthropicClient

HELDOUT_PATH = Path(harness.__file__).parent / "heldout_representative.json"
OUTPUT_PATH = Path("quality_calibration.json")
THRESHOLDS = [4, 5, 6, 7, 8]


def main() -> None:
    dataset = harness.load_dataset(HELDOUT_PATH)
    usage_sink = ListUsageSink()
    llm = AnthropicClient(usage_sink=usage_sink)
    report = harness.evaluate(dataset, harness.make_llm_scorer(llm))

    table = [
        {
            "threshold": threshold,
            "precision": round(
                precision_at_threshold(report.predictions, report.labels, threshold),
                4,
            ),
            "recall": round(
                recall_at_threshold(report.predictions, report.labels, threshold), 4
            ),
        }
        for threshold in THRESHOLDS
    ]

    payload = {
        "source": "heldout_pme_automation (held-out représentatif, module 3.5)",
        "n": len(dataset),
        "thresholds": table,
        "usage": usage_sink.total().model_dump(mode="json"),
        "items": [
            {"title": item.title, "human_label": label, "model_score": pred}
            for item, label, pred in zip(
                dataset, report.labels, report.predictions, strict=True
            )
        ],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Calibration (n={payload['n']}, held-out représentatif)")
    print(f"{'seuil':>5} | {'précision':>9} | {'rappel':>7}")
    for row in table:
        precision, recall = row["precision"], row["recall"]
        print(f"{row['threshold']:>5} | {precision:>9.4f} | {recall:>7.4f}")
    print(f"Coût du run : {usage_sink.total().cost_usd:.4f} USD")


if __name__ == "__main__":
    main()
