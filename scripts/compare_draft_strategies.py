"""Compare single-call (``build_draft_prompt``) vs decomposed (AngleAgent +
WriterAgent) on real items, with real LLM calls (module 4.2).

Uses the 10 "highly relevant" items (label >= 8) of the module 3.5 sealed
held-out (``heldout_representative.json``) — the real population that
would reach the drafting step in production (``min_score = 8``).

Writes ``results/draft_strategy_comparison.json``: both drafts per item (or "no
angle" on the decomposed side) + the real cost (module 3.4) of each
strategy. Quality judgment (faithfulness/angle/actionability) is then done
by hand on that file — outside this script, see ANGLE_AGENT.md.

    uv run python scripts/compare_draft_strategies.py
"""
import json
from pathlib import Path

from core.usage import ListUsageSink
from radar.drafting.angle import decide_angle
from radar.drafting.parse import parse_draft
from radar.drafting.prompt import build_draft_prompt
from radar.drafting.writer import write_draft
from radar.eval import harness
from radar.llm.anthropic_client import AnthropicClient

HELDOUT_PATH = Path(harness.__file__).parent / "heldout_representative.json"
OUTPUT_PATH = Path("results/draft_strategy_comparison.json")
MIN_LABEL_VERY_RELEVANT = 8


def main() -> None:
    dataset = harness.load_dataset(HELDOUT_PATH)
    items = [item for item in dataset if item.label >= MIN_LABEL_VERY_RELEVANT]

    mono_sink = ListUsageSink()
    mono_llm = AnthropicClient(usage_sink=mono_sink, max_tokens=512)

    decomposed_sink = ListUsageSink()
    decomposed_llm = AnthropicClient(usage_sink=decomposed_sink, max_tokens=512)

    results = []
    for item in items:
        mono_prompt = build_draft_prompt(item)
        mono_draft = parse_draft(mono_llm.complete(mono_prompt))

        angle = decide_angle(item, decomposed_llm)
        decomposed_draft = (
            write_draft(item, angle, decomposed_llm).text if angle.has_angle else None
        )

        results.append(
            {
                "title": item.title,
                "human_label": item.label,
                "mono_draft": mono_draft.text,
                "angle_has_angle": angle.has_angle,
                "angle_text": angle.angle,
                "decomposed_draft": decomposed_draft,
            }
        )

    payload = {
        "source": "heldout_representative.json, items label>=8 (module 4.2)",
        "n_items": len(items),
        "mono_usage": mono_sink.total().model_dump(mode="json"),
        "decomposed_usage": decomposed_sink.total().model_dump(mode="json"),
        "n_decomposed_drafted": sum(
            1 for r in results if r["decomposed_draft"] is not None
        ),
        "n_decomposed_skipped_no_angle": sum(
            1 for r in results if r["decomposed_draft"] is None
        ),
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"n_items = {payload['n_items']}")
    print(f"Mono       : {mono_sink.total().cost_usd:.4f} USD")
    print(f"Decomposed : {decomposed_sink.total().cost_usd:.4f} USD")
    print(
        f"Decomposed: {payload['n_decomposed_drafted']} drafted, "
        f"{payload['n_decomposed_skipped_no_angle']} sans angle (skip)"
    )
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
