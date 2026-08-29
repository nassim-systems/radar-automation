"""Contrôle du seuil retenu sur un échantillon réel non filtré (module 3.5,
point 4 — substitut au batch exact du run 3.3, non conservé, cf.
``label_production_recall_check.py``).

Hors suite de tests : vrais appels LLM. Charge
``src/radar/eval/production_recall_check.json`` (20 items réels, non
sélectionnés vers un palier — échantillon non biaisé), le score avec le vrai
modèle, et rapporte comment ``min_score`` (retenu dans ``composition.py``) se
comporterait dessus.

    uv run python scripts/check_production_recall.py
"""
import json
from pathlib import Path

from radar.eval import harness
from radar.llm.anthropic_client import AnthropicClient
from radar.llm.usage import ListUsageSink

DATASET_PATH = Path(harness.__file__).parent / "production_recall_check.json"
OUTPUT_PATH = Path("production_recall_check_results.json")
MIN_SCORE = 8  # doit rester synchronisé avec composition.py::_MIN_SCORE


def main() -> None:
    dataset = harness.load_dataset(DATASET_PATH)
    usage_sink = ListUsageSink()
    llm = AnthropicClient(usage_sink=usage_sink)
    report = harness.evaluate(dataset, harness.make_llm_scorer(llm))

    retained = [
        (item.title, label, pred)
        for item, label, pred in zip(
            dataset, report.labels, report.predictions, strict=True
        )
        if pred >= MIN_SCORE
    ]
    n_truly_relevant = sum(1 for label in report.labels if label >= MIN_SCORE)
    n_false_positives = sum(1 for _, label, _ in retained if label < MIN_SCORE)

    payload = {
        "source": "production_recall_check (échantillon réel non biaisé, module 3.5)",
        "n": len(dataset),
        "min_score": MIN_SCORE,
        "n_retained_at_min_score": len(retained),
        "n_truly_relevant_in_sample": n_truly_relevant,
        "n_false_positives_at_min_score": n_false_positives,
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

    print(f"Contrôle rappel réel (n={payload['n']}, échantillon non filtré)")
    print(f"  Items vraiment pertinents (label >= {MIN_SCORE}) : {n_truly_relevant}")
    print(f"  Retenus par min_score={MIN_SCORE} : {len(retained)}")
    print(f"  Faux positifs à ce seuil : {n_false_positives}")
    print(f"  Coût du run : {usage_sink.total().cost_usd:.4f} USD")


if __name__ == "__main__":
    main()
