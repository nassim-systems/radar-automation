import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import EXIT_ALERT, EXIT_CONFIG_ERROR, EXIT_OK, main
from radar.llm.usage import LlmUsage
from radar.observability.models import RunRecord
from radar.pipeline import PipelineReport
from settings import Settings

REPO = Path(__file__).resolve().parents[1]


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


def test_entrypoint_runs_with_fake_pipeline(tmp_path: Path) -> None:
    record = _fake_record()

    def _fake_build(settings: Settings) -> Callable[[], RunRecord]:
        return lambda: record

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(env, build=_fake_build, out=str(out))

    assert code == EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))  # UTF-8 explicite
    assert payload["n_fetched"] == record.report.n_fetched
    assert payload["n_drafted"] == record.report.n_drafted


def test_entrypoint_exit_code_on_missing_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def _never_build(settings: Settings) -> Callable[[], RunRecord]:
        raise AssertionError("build ne doit pas être atteint si la config manque")

    out = tmp_path / "run_report.json"
    code = main(
        {"FEED_URLS": "https://x.example/feed"}, build=_never_build, out=str(out)
    )

    assert code == EXIT_CONFIG_ERROR
    assert "Configuration manquante" in capsys.readouterr().err
    assert not out.exists()  # aucun rapport écrit si la config manque


def test_entrypoint_returns_alert_exit_code_on_cost_over_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _fake_record(cost_usd=999.0)  # largement au-dessus du seuil par défaut

    def _fake_build(settings: Settings) -> Callable[[], RunRecord]:
        return lambda: record

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(env, build=_fake_build, out=str(out))

    assert code == EXIT_ALERT
    assert "ALERTE" in capsys.readouterr().err
    assert out.exists()  # le rapport est quand même écrit malgré l'alerte


def test_entrypoint_returns_alert_exit_code_on_llm_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _fake_record(n_failures=1)

    def _fake_build(settings: Settings) -> Callable[[], RunRecord]:
        return lambda: record

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(env, build=_fake_build, out=str(out))

    assert code == EXIT_ALERT
    assert "ALERTE" in capsys.readouterr().err


def test_scheduling_is_documented() -> None:
    doc = (REPO / "docs" / "ordonnancement.md").read_text(encoding="utf-8").lower()

    assert "cron" in doc
    assert "task scheduler" in doc or "schtasks" in doc
