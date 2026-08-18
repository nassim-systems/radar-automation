"""Évaluation out-of-sample : score le held-out annoté et compare aux labels.

Hors suite de tests : vrais appels LLM. Charge le jeu held-out figé et annoté
(``src/radar/eval/heldout_labeled.json``), le score avec le vrai modèle, calcule
Agreement + Spearman entre labels humains et scores modèle, écrit ``heldout.json``.

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
        "source": "numerama (held-out, hors entraînement)",
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
