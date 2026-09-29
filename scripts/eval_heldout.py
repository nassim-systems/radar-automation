"""Out-of-sample evaluation: score the annotated held-out, compare to labels.

Outside the test suite: real LLM calls. Loads the frozen, annotated held-out
set (``src/radar/eval/heldout_labeled.json``), scores it with the real model,
computes Agreement + Spearman (human labels vs model), writes ``heldout.json``.

    uv run python scripts/eval_heldout.py
"""
import json
from pathlib import Path

from radar.eval import harness
from radar.eval.metrics import spearman
from radar.llm.anthropic_client import AnthropicClient

HELDOUT_LABELED = Path(harness.__file__).parent / "heldout_labeled.json"
OUTPUT_PATH = Path("heldout.json")


def main() -> None:
    dataset = harness.load_dataset(HELDOUT_LABELED)
    report = harness.evaluate(dataset, harness.make_llm_scorer(AnthropicClient()))
    rho = spearman(report.predictions, report.labels)

    payload = {
        "source": "numerama (held-out, out-of-sample)",
        "n": len(dataset),
        "agreement": round(report.metric_value, 4),
        "spearman": round(rho, 4),
        "items": [
            {"title": item.title, "human_label": label, "model_score": pred}
            for item, label, pred in zip(
                dataset, report.labels, report.predictions, strict=True
            )
        ],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Out-of-sample (n={payload['n']}, source held-out Numerama)")
    print(f"  Agreement = {payload['agreement']}")
    print(f"  Spearman  = {payload['spearman']}")


if __name__ == "__main__":
    main()
