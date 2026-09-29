"""Time the human work that the radar replaces (module 4.6).

Turns the default assumptions of ``radar/observability/value.py`` into a
**measurement**. The protocol is deliberately rudimentary — a stopwatch and
one person — but it has the property that matters: the triaged items are
those of a real run (read from ``run_trace.json``), not examples picked for
the exercise.

What this script does not do: it measures only **one** annotator, once.
This is the same non-independence limit as everywhere else in this project
(see ``QUALITY.md``, ``ANGLE_AGENT.md``) — acknowledged, not hidden. The
result remains infinitely preferable to an invented figure, and it is marked
``measured=true`` so it is never mistaken for an assumption —
**only if the operator explicitly confirms** having really timed it
(``_is_measured_confirmed``); any other answer forces
``measured=false``, never the reverse by default.

Usage:

    uv run python scripts/measure_human_baseline.py [run_trace.json]
"""
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar.observability.trace import RunTrace  # noqa: E402
from radar.observability.value import (  # noqa: E402
    HumanBaseline,
    write_human_baseline,
)

DEFAULT_TRACE = REPO / "run_trace.json"
DEFAULT_OUT = REPO / "human_baseline.json"
MAX_ITEMS = 12
DEFAULT_HOURLY_COST_EUR = 50.0
DEFAULT_RUNS_PER_MONTH = 21
DEFAULT_EUR_PER_USD = 0.92


def _chrono(label: str) -> float:
    """Measure the time between two Enter presses. ``time.monotonic``: unaffected by
    a clock adjustment during the measurement."""
    input(f"{label}\n  → Press Enter to START…")
    started = time.monotonic()
    input("  → Press Enter when DONE…")
    elapsed = time.monotonic() - started
    print(f"  ⏱  {elapsed:.1f} s\n")
    return elapsed


def _is_measured_confirmed(response: str) -> bool:
    """``True`` only if the operator answered exactly "yes"
    (insensitive to case and extra whitespace) — any other answer,
    including an empty input (Enter pressed without thinking), forces
    ``measured=False``. Pure function, testable without mocking ``input``.
    """
    return response.strip().lower() == "yes"


def _ask_float(label: str, default: float) -> float:
    raw = input(f"{label} [{default}] : ").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        print(f"  unreadable value, keeping {default}")
        return default


def _measure_triage(trace: RunTrace) -> float | None:
    """Time the triage of **real** items from the latest run."""
    items = trace.items[:MAX_ITEMS]
    if not items:
        print("No item in the trace: cannot time the triage.")
        return None

    print(
        f"\n=== 1/3 — Tri ({len(items)} real items from the run of "
        f"{trace.run_at:%Y-%m-%d}) ===\n"
        "For each item: read the title (open the URL if you really would), "
        "decide whether it deserves a post, then confirm.\n"
    )
    durations: list[float] = []
    for position, item in enumerate(items, start=1):
        print(f"[{position}/{len(items)}] {item.subject.title}")
        if item.subject.url:
            print(f"          {item.subject.url}")
        durations.append(_chrono("  Triage this item"))
    mean = sum(durations) / len(durations)
    print(f"→ Triage: {mean:.1f} s/item on average (n={len(durations)})\n")
    return mean


def main() -> int:
    trace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE
    if not trace_path.exists():
        print(
            f"Trace not found: {trace_path}\n"
            "Run the radar first (`uv run radar-run`) — the timing is based "
            "on the real items of that run, not on examples.",
            file=sys.stderr,
        )
        return 2

    trace = RunTrace.model_validate_json(trace_path.read_text(encoding="utf-8"))
    triage = _measure_triage(trace)
    if triage is None:
        return 2

    print("=== 2/3 — Drafting ===")
    print("Write a complete post from one of these articles, as you would")
    print("really publish it.\n")
    drafting = _chrono("  Write a post end to end")

    print("=== 3/3 — Review ===")
    print("Review a draft produced by the radar (run_report.json) and")
    print("decide whether to publish, fix or discard it.\n")
    review = _chrono("  Review and validate a draft")

    print("=== Economic parameters ===")
    hourly = _ask_float("Loaded hourly cost (EUR/h)", DEFAULT_HOURLY_COST_EUR)
    runs = _ask_float("Runs per month", float(DEFAULT_RUNS_PER_MONTH))
    rate = _ask_float("EUR per USD rate", DEFAULT_EUR_PER_USD)

    print("=== Confirmation ===")
    response = input("Did you actually time it? (yes/no): ")
    measured = _is_measured_confirmed(response)
    if measured:
        note = (
            f"Timed on {len(trace.items[:MAX_ITEMS])} real items from the run "
            f"of {trace.run_at:%Y-%m-%d}; a single annotator, a single pass "
            "(same non-independence limit as QUALITY.md)."
        )
    else:
        print(
            "  Answer other than \"yes\": measured is forced to false. "
            "The default hypotheses stay in use until a confirmed "
            "timing has been done."
        )
        note = (
            "measured=false: the operator confirmation was not exactly "
            "\"yes\" — the times above must not be treated as a real "
            "timing."
        )

    baseline = HumanBaseline(
        seconds_per_item_triage=round(triage, 1),
        seconds_per_draft=round(drafting, 1),
        seconds_per_draft_review=round(review, 1),
        hourly_cost_eur=hourly,
        runs_per_month=int(runs),
        eur_per_usd=rate,
        measured=measured,
        measured_at=datetime.now(tz=UTC),
        note=note,
    )
    write_human_baseline(baseline, DEFAULT_OUT)
    print(f"\nBaseline written to {DEFAULT_OUT} (measured={measured}).")
    if measured:
        print(
            "The next run will use it automatically "
            "(value.baseline.measured = true)."
        )
    else:
        print("The next run will keep using the default hypotheses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
