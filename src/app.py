import os
import sys
from collections.abc import Callable, Mapping

from composition import build_radar_pipeline
from radar.observability.alert import check_alert
from radar.observability.trace import RadarRunOutcome, write_trace_json
from radar.observability.value import compute_value_equation, load_human_baseline
from radar.pipeline import write_report_json
from settings import MissingSettingError, Settings, load_settings

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_ALERT = 3
DEFAULT_REPORT_PATH = "run_report.json"
DEFAULT_TRACE_PATH = "run_trace.json"
DEFAULT_BASELINE_PATH = "human_baseline.json"
MAX_COST_USD_ALERT = 1.0  # cost/run alert threshold (module 3.4)

Builder = Callable[[Settings], Callable[[], RadarRunOutcome]]


def main(  # noqa: PLR0913
    env: Mapping[str, str] | None = None,
    *,
    build: Builder = build_radar_pipeline,
    out: str = DEFAULT_REPORT_PATH,
    trace_out: str = DEFAULT_TRACE_PATH,
    baseline_path: str = DEFAULT_BASELINE_PATH,
) -> int:
    """Load the config, wire and run the radar pipeline, write the report.

    Console entry point (``radar-run`` command): ``env`` defaults to
    ``os.environ`` so it can be called with no argument. Writes ``out`` with
    explicit UTF-8 (independent of any shell redirection).

    Exit codes: 0 = success; 2 = missing configuration (stderr);
    3 = alert (run cost or LLM failures above threshold — stderr). The
    report is written before the alert check: an alert does not prevent
    having the report at hand.

    **Two artifacts, two responsibilities** (module 4.6, ``OBSERVABILITY.md``)
    : ``out`` receives the ``PipelineReport`` with unchanged schema,
    ``trace_out`` the detailed trace of the same run. The value equation is
    applied here, not in the composition, because it rests on **business
    assumptions** (``baseline_path``) rather than measurement: the runner
    measures, the entry point interprets. Without a baseline file, the
    default assumptions are used and flagged as such
    (``value.baseline.measured = false``).
    """
    if env is None:
        env = os.environ
    try:
        settings = load_settings(env)
    except MissingSettingError as error:
        print(f"Configuration manquante : {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    outcome = build(settings)()
    record = outcome.record
    write_report_json(record.report, out)
    trace = outcome.trace.model_copy(
        update={
            "value": compute_value_equation(
                report=record.report,
                machine_seconds=outcome.trace.latency.run_seconds,
                machine_cost_usd=record.usage.cost_usd,
                baseline=load_human_baseline(baseline_path),
            )
        }
    )
    write_trace_json(trace, trace_out)
    print(
        f"Report written to {out} ({record.report.n_drafted} draft(s), "
        f"{record.report.n_above_threshold} above threshold, "
        f"{record.usage.cost_usd:.4f} USD, "
        f"{trace.latency.run_seconds:.1f} s)."
    )
    print(
        f"Trace written to {trace_out} "
        f"({trace.n_llm_calls_traced} LLM call(s), "
        f"{trace.latency.llm_cumulative_seconds:.1f} s cumulative)."
    )
    alert = check_alert(record, max_cost_usd=MAX_COST_USD_ALERT)
    if alert is not None:
        print(f"ALERTE : {alert}", file=sys.stderr)
        return EXIT_ALERT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
