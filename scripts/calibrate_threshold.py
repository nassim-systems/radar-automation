"""Calibrate ``min_score``: precision/recall on the representative held-out
at several thresholds.

Outside the test suite: real LLM calls. Loads the sealed held-out
(``src/radar/eval/heldout_representative.json``), scores it with the real
model, computes precision_at_threshold/recall_at_threshold for each threshold
in ``THRESHOLDS``, writes ``results/quality_calibration.json``. This script's results
feed ``QUALITY.md`` (module 3.5).

    uv run python scripts/calibrate_threshold.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.eval import harness
from radar.eval.metrics import precision_at_threshold, recall_at_threshold
from radar.llm.anthropic_client import AnthropicClient

HELDOUT_PATH = Path(harness.__file__).parent / "heldout_representative.json"
OUTPUT_PATH = Path("results/quality_calibration.json")
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
        "source": "heldout_pme_automation (representative held-out, module 3.5)",
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
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Calibration (n={payload['n']}, representative held-out)")
    print(f"{'seuil':>5} | {'precision':>9} | {'rappel':>7}")
    for row in table:
        precision, recall = row["precision"], row["recall"]
        print(f"{row['threshold']:>5} | {precision:>9.4f} | {recall:>7.4f}")
    print(f"Run cost: {usage_sink.total().cost_usd:.4f} USD")


if __name__ == "__main__":
    main()
