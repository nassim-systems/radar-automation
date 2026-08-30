"""Mesure la valeur réelle du CriticAgent (module 4.4) sur le jeu de
brouillons de ``radar/eval/critic_test_set.py`` (6 bons + 8 volontairement
défectueux, 2 par catégorie), avec de vrais appels LLM.

Calcule le taux de détection (rappel sur les 8 défectueux) et le taux de
faux rejets (sur les 6 bons), et écrit le détail par item dans
``critic_agent_measurement.json``. Le verdict garder/jeter (§ANGLE_AGENT.md
puis ce module : ``CRITIC_AGENT.md``) se décide sur ces chiffres, pas avant.

    uv run python scripts/measure_critic_agent.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.drafting.critic import critique_draft
from radar.eval.critic_test_set import CRITIC_TEST_SET
from radar.llm.anthropic_client import AnthropicClient

OUTPUT_PATH = Path("critic_agent_measurement.json")


_MAX_TOKENS = 256  # le défaut (16) est dimensionné pour le scoring, insuffisant
# pour "VERDICT: ..." + "RAISONS: ..." — cause de troncature déjà rencontrée
# pour le drafting en 3.3 (_LLM_MAX_TOKENS) ; même correction ici.


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
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"n={payload['n_total']} "
        f"({payload['n_defective']} défectueux, {payload['n_good']} bons)"
    )
    print(
        f"Détection  : {n_detected}/{len(defective)} "
        f"({payload['detection_rate']:.0%})"
    )
    print(
        f"Faux rejets: {n_false_rejections}/{len(good)} "
        f"({payload['false_rejection_rate']:.0%})"
    )
    print(f"Coût       : {sink.total().cost_usd:.4f} USD")
    print(f"Écrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
