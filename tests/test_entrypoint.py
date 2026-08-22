import json
from collections.abc import Callable
from pathlib import Path

import pytest

from app import main
from radar.pipeline import PipelineReport
from settings import Settings

REPO = Path(__file__).resolve().parents[1]


def _fake_report() -> PipelineReport:
    return PipelineReport(
        n_fetched=3,
        n_dedup=3,
        n_fresh=2,
        n_unseen=2,
        n_scored=2,
        n_drafted=0,
        n_llm_calls=2,
        n_failures=0,
        drafts=[],
    )


def test_entrypoint_runs_with_fake_pipeline(tmp_path: Path) -> None:
    report = _fake_report()

    def _fake_build(settings: Settings) -> Callable[[], PipelineReport]:
        return lambda: report

    out = tmp_path / "run_report.json"
    env = {"ANTHROPIC_API_KEY": "test-key", "FEED_URLS": "https://x.example/feed"}
    code = main(env, build=_fake_build, out=str(out))

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))  # UTF-8 explicite
    assert payload["n_fetched"] == report.n_fetched
    assert payload["n_drafted"] == report.n_drafted


def test_entrypoint_exit_code_on_missing_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def _never_build(settings: Settings) -> Callable[[], PipelineReport]:
        raise AssertionError("build ne doit pas être atteint si la config manque")

    out = tmp_path / "run_report.json"
    code = main(
        {"FEED_URLS": "https://x.example/feed"}, build=_never_build, out=str(out)
    )

    assert code != 0
    assert "Configuration manquante" in capsys.readouterr().err
    assert not out.exists()  # aucun rapport écrit si la config manque


def test_scheduling_is_documented() -> None:
    doc = (REPO / "docs" / "ordonnancement.md").read_text(encoding="utf-8").lower()

    assert "cron" in doc
    assert "task scheduler" in doc or "schtasks" in doc
