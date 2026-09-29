"""Check the chosen threshold on a real, unfiltered sample (module 3.5,
point 4 — substitute for the exact batch of run 3.3, not kept, see
``label_production_recall_check.py``).

Outside the test suite: real LLM calls. Loads
``src/radar/eval/production_recall_check.json`` (20 real items, not
selected toward any tier — unbiased sample), scores it with the real
model, and reports how ``min_score`` (chosen in ``composition.py``) would
behave on it.

    uv run python scripts/check_production_recall.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.eval import harness
from radar.llm.anthropic_client import AnthropicClient

DATASET_PATH = Path(harness.__file__).parent / "production_recall_check.json"
OUTPUT_PATH = Path("results/production_recall_check_results.json")
MIN_SCORE = 8  # must stay in sync with composition.py::_MIN_SCORE


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
        "source": "production_recall_check (unbiased real sample, module 3.5)",
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
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Real recall check (n={payload['n']}, unfiltered sample)")
    print(f"  Items vraiment pertinents (label >= {MIN_SCORE}) : {n_truly_relevant}")
    print(f"  Kept by min_score={MIN_SCORE} : {len(retained)}")
    print(f"  False positives at this threshold: {n_false_positives}")
    print(f"  Run cost: {usage_sink.total().cost_usd:.4f} USD")


if __name__ == "__main__":
    main()
