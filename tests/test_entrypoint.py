import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import EXIT_ALERT, EXIT_CONFIG_ERROR, EXIT_OK, main
from core.usage import LlmUsage
from radar.observability.models import RunRecord
from radar.observability.trace import (
    LatencySummary,
    RadarRunOutcome,
    RunCounters,
    RunTrace,
)
from radar.pipeline import PipelineReport
from settings import Settings

REPO = Path(__file__).resolve().parents[1]
FAKE_RUN_SECONDS = 1.5


def _fake_report(*, n_failures: int = 0) -> PipelineReport:
    return PipelineReport(
        n_fetched=3,
        n_dedup=3,
        n_fresh=2,
        n_unseen=2,
        n_scored=2,
        n_above_threshold=2,
        n_drafted=0,
        n_llm_calls=2,
        n_failures=n_failures,
        drafts=[],
    )


def _fake_record(*, cost_usd: float = 0.01, n_failures: int = 0) -> RunRecord:
    return RunRecord(
        at=datetime.now(tz=UTC),
        report=_fake_report(n_failures=n_failures),
        usage=LlmUsage(input_tokens=100, output_tokens=20, cost_usd=cost_usd),
    )


def _fake_outcome(*, cost_usd: float = 0.01, n_failures: int = 0) -> RadarRunOutcome:
    record = _fake_record(cost_usd=cost_usd, n_failures=n_failures)
    now = datetime.now(tz=UTC)
    return RadarRunOutcome(
        record=record,
        trace=RunTrace(
            run_at=record.at,
            started_at=now,
            ended_at=now,
            counters=RunCounters(**record.report.model_dump(exclude={"drafts"})),
            latency=LatencySummary(
                run_seconds=FAKE_RUN_SECONDS,
                steps_seconds=1.4,
                orchestration_seconds=0.1,
                llm_cumulative_seconds=2.0,
                llm_mean_call_seconds=1.0,
                llm_slowest_call_seconds=1.2,
                slowest_step="score",
                slowest_step_seconds=1.2,
            ),
            usage=record.usage,
            n_llm_calls_traced=record.report.n_llm_calls,
        ),
    )


def test_entrypoint_runs_with_fake_pipeline(tmp_path: Path) -> None:
    outcome = _fake_outcome()

    def _fake_build(settings: Settings) -> Callable[[], RadarRunOutcome]:
        return lambda: outcome

    out = tmp_path / "run_report.json"
    trace_out = tmp_path / "run_trace.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(
        env,
        build=_fake_build,
        out=str(out),
        trace_out=str(trace_out),
        baseline_path=str(tmp_path / "absent.json"),
    )

    assert code == EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))  # UTF-8 explicite
    assert payload["n_fetched"] == outcome.record.report.n_fetched
    assert payload["n_drafted"] == outcome.record.report.n_drafted
    # The report keeps its schema: the trace lives in its own artifact.
    assert "latency" not in payload
    assert "value" not in payload


def test_entrypoint_writes_a_separate_trace_with_the_value_equation(
    tmp_path: Path,
) -> None:
    outcome = _fake_outcome()

    def _fake_build(settings: Settings) -> Callable[[], RadarRunOutcome]:
        return lambda: outcome

    out = tmp_path / "run_report.json"
    trace_out = tmp_path / "run_trace.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(
        env,
        build=_fake_build,
        out=str(out),
        trace_out=str(trace_out),
        baseline_path=str(tmp_path / "absent.json"),
    )

    assert code == EXIT_OK
    trace = json.loads(trace_out.read_text(encoding="utf-8"))
    assert trace["latency"]["run_seconds"] == FAKE_RUN_SECONDS
    assert trace["counters"]["n_scored"] == outcome.record.report.n_scored
    # The equation is applied at the entry point, not by the runner...
    assert trace["value"] is not None
    # ...and without a baseline file, it announces itself as unmeasured.
    assert trace["value"]["baseline"]["measured"] is False


def test_entrypoint_exit_code_on_missing_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def _never_build(settings: Settings) -> Callable[[], RadarRunOutcome]:
        raise AssertionError("build ne doit pas être atteint si la config manque")

    out = tmp_path / "run_report.json"
    code = main(
        {"FEED_URLS": "https://x.example/feed"}, build=_never_build, out=str(out)
    )

    assert code == EXIT_CONFIG_ERROR
    assert "Configuration manquante" in capsys.readouterr().err
    assert not out.exists()  # no report written if the config is missing


def test_entrypoint_returns_alert_exit_code_on_cost_over_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outcome = _fake_outcome(cost_usd=999.0)  # above the default threshold

    def _fake_build(settings: Settings) -> Callable[[], RadarRunOutcome]:
        return lambda: outcome

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(
        env,
        build=_fake_build,
        out=str(out),
        trace_out=str(tmp_path / "run_trace.json"),
        baseline_path=str(tmp_path / "absent.json"),
    )

    assert code == EXIT_ALERT
    assert "ALERTE" in capsys.readouterr().err
    assert out.exists()  # the report is still written despite the alert


def test_entrypoint_returns_alert_exit_code_on_llm_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outcome = _fake_outcome(n_failures=1)

    def _fake_build(settings: Settings) -> Callable[[], RadarRunOutcome]:
        return lambda: outcome

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(
        env,
        build=_fake_build,
        out=str(out),
        trace_out=str(tmp_path / "run_trace.json"),
        baseline_path=str(tmp_path / "absent.json"),
    )

    assert code == EXIT_ALERT
    assert "ALERTE" in capsys.readouterr().err


def test_scheduling_is_documented() -> None:
    doc = (REPO / "docs" / "scheduling.md").read_text(encoding="utf-8").lower()

    assert "cron" in doc
    assert "task scheduler" in doc or "schtasks" in doc
