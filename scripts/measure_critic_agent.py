"""Measure the real value of the CriticAgent (module 4.4) on the draft set from
``radar/eval/critic_test_set.py`` (6 good + 8 deliberately defective, 2 per
category), with real LLM calls.

Computes the detection rate (recall on the 8 defective) and the false reject
rate (on the 6 good), and writes per-item detail to
``results/critic_agent_measurement.json``. The keep/drop verdict (§ANGLE_AGENT.md
then this module: ``CRITIC_AGENT.md``) is decided on these numbers, not before.

    uv run python scripts/measure_critic_agent.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.drafting.critic import critique_draft
from radar.eval.critic_test_set import CRITIC_TEST_SET
from radar.llm.anthropic_client import AnthropicClient

OUTPUT_PATH = Path("results/critic_agent_measurement.json")


_MAX_TOKENS = 256  # the default (16) is sized for scoring, insufficient
# for "VERDICT: ..." + "RAISONS: ..." — truncation cause already hit
# for drafting in 3.3 (_LLM_MAX_TOKENS); same fix here.


def main() -> None:
    sink = ListUsageSink()
    llm = AnthropicClient(usage_sink=sink, max_tokens=_MAX_TOKENS)

    results = []
    for case in CRITIC_TEST_SET:
        verdict = critique_draft(case.item, case.draft, llm)
        correct = verdict.accepted == case.expected_accepted
        results.append(
            {
                "id": case.id,
                "expected_accepted": case.expected_accepted,
                "defect_category": case.defect_category,
                "actual_accepted": verdict.accepted,
                "reasons": verdict.reasons,
                "correct": correct,
            }
        )

    defective = [r for r in results if not r["expected_accepted"]]
    good = [r for r in results if r["expected_accepted"]]
    n_detected = sum(1 for r in defective if not r["actual_accepted"])
    n_false_rejections = sum(1 for r in good if not r["actual_accepted"])

    payload = {
        "n_total": len(results),
        "n_defective": len(defective),
        "n_good": len(good),
        "n_detected": n_detected,
        "detection_rate": n_detected / len(defective) if defective else None,
        "n_false_rejections": n_false_rejections,
        "false_rejection_rate": n_false_rejections / len(good) if good else None,
        "usage": sink.total().model_dump(mode="json"),
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"n={payload['n_total']} "
        f"({payload['n_defective']} defective, {payload['n_good']} bons)"
    )
    print(
        f"Detection  : {n_detected}/{len(defective)} "
        f"({payload['detection_rate']:.0%})"
    )
    print(
        f"Faux rejets: {n_false_rejections}/{len(good)} "
        f"({payload['false_rejection_rate']:.0%})"
    )
    print(f"Coût       : {sink.total().cost_usd:.4f} USD")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
