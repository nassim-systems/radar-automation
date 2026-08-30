from datetime import UTC, datetime

from core.usage import LlmUsage
from radar.observability.alert import check_alert
from radar.observability.models import RunRecord
from radar.pipeline import PipelineReport

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
MAX_COST_USD = 1.0


def _report(*, n_failures: int = 0) -> PipelineReport:
    return PipelineReport(
        n_fetched=1,
        n_dedup=1,
        n_fresh=1,
        n_unseen=1,
        n_scored=1,
        n_above_threshold=1,
        n_drafted=1,
        n_llm_calls=1,
        n_failures=n_failures,
        drafts=[],
    )


def _record(*, cost_usd: float, n_failures: int = 0) -> RunRecord:
    return RunRecord(
        at=NOW,
        report=_report(n_failures=n_failures),
        usage=LlmUsage(input_tokens=10, output_tokens=10, cost_usd=cost_usd),
    )


def test_check_alert_none_when_under_threshold_and_no_failures() -> None:
    record = _record(cost_usd=0.01)

    assert check_alert(record, max_cost_usd=MAX_COST_USD) is None


def test_check_alert_triggers_on_cost_over_threshold() -> None:
    record = _record(cost_usd=5.0)

    alert = check_alert(record, max_cost_usd=MAX_COST_USD)

    assert alert is not None
    assert "5.0000" in alert


def test_check_alert_triggers_on_llm_failures() -> None:
    record = _record(cost_usd=0.0, n_failures=2)

    alert = check_alert(record, max_cost_usd=MAX_COST_USD)

    assert alert is not None
    assert "2" in alert


def test_check_alert_cost_exactly_at_threshold_does_not_trigger() -> None:
    record = _record(cost_usd=MAX_COST_USD)

    assert check_alert(record, max_cost_usd=MAX_COST_USD) is None
