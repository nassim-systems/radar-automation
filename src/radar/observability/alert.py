from radar.observability.models import RunRecord


def check_alert(record: RunRecord, *, max_cost_usd: float) -> str | None:
    """Check a run against a simple threshold: excessive cost or LLM failures.

    Pure function. Returns an alert message if a threshold is exceeded, else
    ``None``. Does not decide the signal (exit code, stderr): that remains
    the caller's responsibility (``app.main``).
    """
    if record.usage.cost_usd > max_cost_usd:
        return (
            f"run cost ({record.usage.cost_usd:.4f} USD) "
            f"> threshold ({max_cost_usd:.4f} USD)"
        )
    if record.report.n_failures > 0:
        return f"{record.report.n_failures} LLM failure(s) during the run"
    return None
